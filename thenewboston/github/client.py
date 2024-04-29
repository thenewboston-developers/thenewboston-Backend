from enum import Enum
from urllib.parse import urljoin

import requests
from django.conf import settings
from github import Auth, Github
from github.PaginatedList import PaginatedList
from github.PullRequest import PullRequest


# TODO(dmu) LOW: Migrate to Python >=3.11 and use StrEnum
class PullRequestState(Enum):
    OPEN = 'open'
    CLOSED = 'closed'
    ALL = 'all'


BASE_URL = 'https://api.github.com/'


def make_url(path):
    return urljoin(BASE_URL, path)


class GitHubClient:

    def __init__(self):
        self.access_token = access_token = settings.GITHUB_API_ACCESS_TOKEN
        self.client = Github(auth=Auth.Token(access_token))

    def get_pull_requests(
        self,
        repo_owner,
        repo_name,
        state: PullRequestState = PullRequestState.CLOSED,
        base: str | None = None,
    ) -> PaginatedList[PullRequest]:
        # TODO(dmu) LOW: Better handle non-existing owner or repo
        repo = self.client.get_repo(f'{repo_owner}/{repo_name}')

        kwargs = {'base': base} if base else {}
        return repo.get_pulls(state=state.value, sort='created', **kwargs)

    def get_pull_request_diff(self, repo_owner, repo_name, pull_request_issue_number):
        # We are not using `diff_url` from the PR because it will not work for private repositories
        # We are not using github.Github() because it does seem to allow requesting PR diffs
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/vnd.github.diff',
        }
        url = make_url(f'/repos/{repo_owner}/{repo_name}/pulls/{pull_request_issue_number}')
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
