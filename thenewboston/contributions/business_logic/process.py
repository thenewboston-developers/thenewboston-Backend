import logging

from thenewboston.contributions.business_logic.base import get_repos
from thenewboston.contributions.models import Contribution
from thenewboston.contributions.models.contribution import ContributionType
from thenewboston.cores.utils.core import get_default_core
from thenewboston.general.utils.logging import log
from thenewboston.github.models import Pull, Repo

from .base import transaction_atomic

logger = logging.getLogger(__name__)


def create_pull_request_contribution(core, pull_request):
    github_user = pull_request.github_user
    reward_recipient = github_user.reward_recipient
    assert reward_recipient

    return Contribution.objects.create(
        contribution_type=ContributionType.PULL_REQUEST.value,
        core=core,
        github_user=github_user,
        pull=pull_request,
        repo=pull_request.repo,
        user=reward_recipient,
        description=pull_request.description,
    )


@log(with_arguments=True, exception_log_level=logging.INFO)
@transaction_atomic
def assess_pull_request(pull_request: Pull):
    pull_request.assess()


@log(with_arguments=True, exception_log_level=logging.INFO)
@transaction_atomic
def reward_contribution(contribution):
    contribution = contribution.select_for_update()
    contribution.assess()
    contribution.reward()


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

    contribution = create_pull_request_contribution(get_default_core(), pull_request)
    assert contribution.contribution_type == ContributionType.PULL_REQUEST.value  # type: ignore
    reward_contribution(contribution)


@log(with_arguments=True)
def process_repo(repo: Repo, limit=None):
    query = repo.pulls.order_by('created_date').filter(contributions__isnull=True)
    if limit is not None:
        query = query[:limit]

    for pull_request in query:
        try:
            assess_pull_request(pull_request)  # purposefully do it in a separate transaction
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
            logger.warning('Error while processing repo: %s', repo, exc_info=True)


@log(with_arguments=True)
def reward_manual_contributions(contribution_id=None):
    # TODO(dmu) LOW: Consider rewarding all contributions here, not just manual
    query = Contribution.objects.filter(contribution_type=ContributionType.MANUAL.value, reward_amount__isnull=True)
    if contribution_id is not None:
        query = query.filter(id=contribution_id)

    for contribution in query:
        try:
            reward_contribution(contribution)
        except Exception:
            logger.warning('Error while rewarding contribution: %s', contribution, exc_info=True)
