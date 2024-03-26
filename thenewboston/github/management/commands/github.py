from itertools import islice

from django.core.management.base import BaseCommand

from thenewboston.github.client import GitHubClient, PullRequestState


class Command(BaseCommand):
    help = 'GitHub CLI for GitHub integration testing and debugging'  # noqa: A003

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(help='subcommand', dest='subcommand')

        list_pull_requests_parser = subparsers.add_parser('get-pull-requests')
        list_pull_requests_parser.add_argument('owner')
        list_pull_requests_parser.add_argument('name')
        list_pull_requests_parser.add_argument(
            '--state',
            '-s',
            choices=[state.value for state in PullRequestState],
            help='Filter by the state of pull requests',
            default=PullRequestState.OPEN.value,
        )
        list_pull_requests_parser.add_argument('--limit', '-l', type=int)

    def handle_get_pull_requests(self, *args, **options):
        pull_requests = GitHubClient().get_pull_requests(
            options['owner'], options['name'], state=PullRequestState(options['state'])
        )
        if (limit := options['limit']) is not None:
            pull_requests = islice(pull_requests, limit)

        for pull_request in pull_requests:
            print(pull_request)

    def handle(self, *args, **options):
        subcommand_handler = getattr(self, f"handle_{options['subcommand'].replace('-', '_')}")
        subcommand_handler(self, *args, **options)
