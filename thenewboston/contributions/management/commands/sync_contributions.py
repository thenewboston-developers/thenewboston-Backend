from django.core.management.base import BaseCommand

from thenewboston.contributions.tasks import sync_contributions


class Command(BaseCommand):
    help = 'Run sync_contributions Celery task manually (for testing and debugging)'  # noqa: A003

    def add_arguments(self, parser):
        parser.add_argument('--repo-id', type=int)
        parser.add_argument('--limit', '-l', type=int)

    def handle(self, *args, **options):
        sync_contributions(repo_id=options['repo_id'], limit=options['limit'])
