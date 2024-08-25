import logging
from itertools import islice

from github.PullRequest import PullRequest

from thenewboston.contributions.business_logic.base import get_repos
from thenewboston.general.utils.logging import log
from thenewboston.github.client import GitHubClient, PullRequestState
from thenewboston.github.models import GitHubUser, Pull, Repo

from .base import transaction_atomic

logger = logging.getLogger(__name__)


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
            'description': pull_request.body or '',
        },
    )


@log(with_arguments=True, exception_log_level=logging.INFO)
def sync_repo(repo, limit=None):
    # TODO(dmu) HIGH: Because we are getting closed PRs the list will grow with time and work slower and slower.
    #                 An optimization is need here, so we only request recent X PRs until we encounter a PR
    #                 we have already synced
    pull_requests = GitHubClient().get_pull_requests(
        repo.owner_name, repo.name, state=PullRequestState.CLOSED, base=repo.contribution_branch
    )
    if limit is not None:
        pull_requests = islice(pull_requests, limit)

    for pull_request in pull_requests:
        try:
            assert pull_request.base.ref == repo.contribution_branch
            if not pull_request.merged:
                continue

            sync_pull_request(repo, pull_request)
        except Exception:
            logger.warning(
                'Error while syncing pull request number %s in repo %s',
                pull_request.number,
                repo,
                exc_info=True,
            )


@log(with_arguments=True)
def sync_repos(repo_id=None, limit=None):
    for repo in get_repos(repo_id):
        try:
            sync_repo(repo, limit=limit)
        except Exception:
            logger.warning('Error while syncing repo: %s', repo, exc_info=True)
