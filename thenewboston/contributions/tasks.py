import logging
from itertools import islice

from celery import shared_task
from django.conf import settings
from django.db import transaction
from github.PullRequest import PullRequest

from thenewboston.contributions.models import Contribution
from thenewboston.cores.models import Core
from thenewboston.general.utils.logging import log
from thenewboston.general.utils.misc import identity_decorator, swallow_exception
from thenewboston.general.utils.pytest import is_pytest_running
from thenewboston.general.utils.transfers import change_wallet_balance
from thenewboston.github.client import GitHubClient, PullRequestState
from thenewboston.github.models import GitHubUser, Pull, Repo

transaction_atomic = identity_decorator if is_pytest_running() else transaction.atomic
logger = logging.getLogger(__name__)


def get_repos(repo_id):
    query = Repo.objects.all()
    if repo_id is not None:
        query = query.filter(id=repo_id)

    return query.all()


def get_default_core():
    return Core.objects.get(ticker=settings.CONTRIBUTION_CORE_DEFAULT_TICKER)


@log(with_arguments=True, exception_log_level=logging.INFO)
@transaction_atomic  # Added for forward compatibility reasons
def sync_pull_request(repo: Repo, pull_request: PullRequest):
    user = pull_request.user
    user_github_id = user.id
    if not (github_user := GitHubUser.objects.get_or_none(github_id=user_github_id)):
        logger.warning(
            'User %s (GitHub ID: %s) is not found in the database (consider creating one)', user.login, user_github_id
        )
        return

    Pull.objects.get_or_create(
        repo=repo,
        issue_number=pull_request.number,
        defaults={
            'title': pull_request.title,
            'github_user': github_user,
        },
    )


@log(with_arguments=True, exception_log_level=logging.INFO)
def sync_repo(repo, limit=None, pull_request_state=None):
    pull_request_state = pull_request_state or PullRequestState(settings.GITHUB_PULL_REQUEST_STATE_FILTER)
    pull_requests = GitHubClient().get_pull_requests(repo.owner_name, repo.name, state=pull_request_state)
    if limit is not None:
        pull_requests = islice(pull_requests, limit)

    for pull_request in pull_requests:
        try:
            sync_pull_request(repo, pull_request)
        except Exception:
            logger.warning(
                'Error while syncing pull request number %s in repo %s',
                pull_request.number,
                repo,
                exc_info=True,
            )


@log(with_arguments=True, exception_log_level=logging.WARNING)
def sync_repos(repo_id=None, limit=None):
    for repo in get_repos(repo_id):
        try:
            sync_repo(repo, limit=limit)
        except Exception:
            logger.warning(
                'Error while syncing repo: %s',
                repo,
                exc_info=True,
            )


def create_contribution(core, pull_request):
    github_user = pull_request.github_user
    reward_recipient = github_user.reward_recipient
    assert reward_recipient

    Contribution.objects.create(
        core=core,
        github_user=github_user,
        pull=pull_request,
        repo=pull_request.repo,
        reward_amount=pull_request.value_points,
        user=reward_recipient,
    )


def reward_contributor(core_id: int, pull_request: Pull):
    github_user = pull_request.github_user
    reward_recipient = github_user.reward_recipient
    assert reward_recipient

    wallet = github_user.get_reward_wallet_for_core(core_id)
    assert wallet

    change_wallet_balance(wallet, pull_request.value_points)


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


@shared_task(name='tasks.sync_contributions')
def sync_contributions(repo_id=None, limit=None):
    swallow_exception(sync_repos, repo_id=repo_id, limit=limit)
    swallow_exception(process_repos, repo_id=repo_id, limit=limit)
