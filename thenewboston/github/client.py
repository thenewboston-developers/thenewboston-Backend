from enum import Enum

from django.conf import settings
from github import Auth, Github
from github.PaginatedList import PaginatedList
from github.PullRequest import PullRequest


# TODO(dmu) LOW: Migrate to Python >=3.11 and use StrEnum
class PullRequestState(Enum):
    OPEN = 'open'
    CLOSED = 'closed'
    ALL = 'all'


class GitHubClient:

    def __init__(self):
        self.client = Github(auth=Auth.Token(settings.GITHUB_API_ACCESS_TOKEN))

    def get_pull_requests(
        self,
        repo_owner,
        repo_name,
        state: PullRequestState = PullRequestState.OPEN,
    ) -> PaginatedList[PullRequest]:
        client = self.client
        # TODO(dmu) LOW: Better handle non-existing owner or repo
        return client.get_repo(f'{repo_owner}/{repo_name}').get_pulls(state=state.value, sort='created')
