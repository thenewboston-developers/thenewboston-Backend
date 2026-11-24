import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from thenewboston.product_analytics.client import get_client
from thenewboston.product_analytics.events import enqueue_event
from thenewboston.product_analytics.models import AnalyticsEvent
from thenewboston.product_analytics.tasks import deliver_product_analytics


class Command(BaseCommand):
    help = 'Verify committed analytics delivery with one internal, personless deployment event.'

    def add_arguments(self, parser):
        parser.add_argument('--deployment-sha', required=True)

    def handle(self, *args, **options):
        sha = options['deployment_sha']
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise CommandError('A full lowercase Git deployment SHA is required.')
        if not settings.POSTHOG_ENABLED or get_client() is None:
            raise CommandError('PostHog is disabled or not configured.')
        key = f'analytics_pipeline_verified:{sha}'
        enqueue_event(
            key,
            'analytics_pipeline_verified',
            {'enabled': True, 'distinct_id': f'deployment:{sha}', 'internal_traffic': True},
            {'deployment_sha': sha},
        )
        event = AnalyticsEvent.objects.get(key=key)
        deliver_product_analytics(str(event.pk))
        event.refresh_from_db()
        if event.delivered_at is None:
            raise CommandError('PostHog did not acknowledge the verification event; it remains queued for retry.')
        self.stdout.write(self.style.SUCCESS(f'Analytics verified for deployment {sha}: {event.pk}'))
