from itertools import islice

from thenewboston.general.commands import CustomCommand
from thenewboston.github.client import GitHubClient, PullRequestState


class Command(CustomCommand):
    help = 'GitHub CLI for GitHub integration testing and debugging'  # noqa: A003

    def add_arguments(self, parser):
        subparsers = self.get_subparsers(parser)

        get_pull_requests_parser = subparsers.add_parser('get-pull-requests')
        get_pull_requests_parser.add_argument('owner')
        get_pull_requests_parser.add_argument('name')
        get_pull_requests_parser.add_argument(
            '--state',
            '-s',
            choices=[state.value for state in PullRequestState],
            help='Filter by the state of pull requests',
            default=PullRequestState.OPEN.value,
        )
        get_pull_requests_parser.add_argument('--limit', '-l', type=int)

        get_pull_request_diff_parser_diff = subparsers.add_parser('get-pull-request-diff')
        get_pull_request_diff_parser_diff.add_argument('owner')
        get_pull_request_diff_parser_diff.add_argument('name')
        get_pull_request_diff_parser_diff.add_argument('number', type=int)

    @staticmethod
    def client():
        return GitHubClient()

    def handle_get_pull_requests(self, *args, **options):
        pull_requests = self.client().get_pull_requests(
            options['owner'], options['name'], state=PullRequestState(options['state'])
        )
        if (limit := options['limit']) is not None:
            pull_requests = islice(pull_requests, limit)

        for pull_request in pull_requests:
            print(pull_request, pull_request.body)

    def handle_get_pull_request_diff(self, *args, **options):
        diff = self.client().get_pull_request_diff(options['owner'], options['name'], options['number'])
        print(diff)
