import logging

from thenewboston.contributions.business_logic.base import get_repos
from thenewboston.contributions.models import Contribution
from thenewboston.cores.utils.core import get_default_core
from thenewboston.general.utils.logging import log
from thenewboston.general.utils.transfers import change_wallet_balance
from thenewboston.github.models import Pull, Repo

from .base import transaction_atomic

logger = logging.getLogger(__name__)


def create_contribution(core, pull_request):
    github_user = pull_request.github_user
    reward_recipient = github_user.reward_recipient
    assert reward_recipient
    assert pull_request.assessment_points is not None

    Contribution.objects.create(
        core=core,
        github_user=github_user,
        pull=pull_request,
        repo=pull_request.repo,
        reward_amount=pull_request.assessment_points,
        user=reward_recipient,
    )


def reward_contributor(core_id: int, pull_request: Pull):
    github_user = pull_request.github_user
    reward_recipient = github_user.reward_recipient
    assert reward_recipient

    wallet = github_user.get_reward_wallet_for_core(core_id)
    assert wallet
    assert pull_request.assessment_points is not None

    change_wallet_balance(wallet, pull_request.assessment_points)


@log(with_arguments=True, exception_log_level=logging.INFO)
@transaction_atomic
def pre_process_pull_request(pull_request: Pull):
    pull_request.assess()


@log(with_arguments=True, exception_log_level=logging.INFO)
@transaction_atomic
def process_pull_request(pull_request: Pull):
    assert not pull_request.contributions.exists()

    github_user = pull_request.github_user
    if not github_user.reward_recipient:
        logger.warning(
            'Reward recipient is not specified for %s (ID: %s) GitHub user, postponing pull request processing',
            github_user.github_username, github_user.github_id
        )
        return

    core = get_default_core()
    create_contribution(core, pull_request)
    reward_contributor(core.id, pull_request)


@log(with_arguments=True)
def process_repo(repo: Repo, limit=None):
    query = repo.pulls.order_by('created_date').filter(contributions__isnull=True)
    if limit is not None:
        query = query[:limit]

    for pull_request in query:
        try:
            pre_process_pull_request(pull_request)  # purposefully do it in a separate transaction
            if pull_request.assessment_points is None:
                logger.warning(
                    'Assessment points were not assigned to pull request number %s in repo %s',
                    pull_request.issue_number,
                    repo,
                )
                continue

            process_pull_request(pull_request)
        except Exception:
            logger.warning(
                'Error while processing pull request number %s in repo %s',
                pull_request.issue_number,
                repo,
                exc_info=True,
            )


@log(with_arguments=True)
def process_repos(repo_id=None, limit=None):
    for repo in get_repos(repo_id):
        try:
            process_repo(repo, limit=limit)
        except Exception:
            logger.warning(
                'Error while processing repo: %s',
                repo,
                exc_info=True,
            )
