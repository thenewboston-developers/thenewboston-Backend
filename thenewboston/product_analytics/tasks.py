import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from thenewboston.project.celery import app

from .client import get_client
from .models import AnalyticsEvent

logger = logging.getLogger(__name__)


@app.task(name='tasks.deliver_product_analytics')
def deliver_product_analytics(only_event_id=None):
    client = get_client()
    if not settings.POSTHOG_ENABLED or client is None:
        return 0
    pending = AnalyticsEvent.objects.filter(delivered_at__isnull=True, next_attempt_at__lte=timezone.now())
    if only_event_id is not None:
        pending = pending.filter(pk=only_event_id)
    event_ids = list(pending.order_by('next_attempt_at').values_list('pk', flat=True)[:20])
    delivered = 0
    for event_id in event_ids:
        with transaction.atomic():
            event = (
                AnalyticsEvent.objects.select_for_update(skip_locked=True)
                .filter(
                    pk=event_id,
                    delivered_at__isnull=True,
                    next_attempt_at__lte=timezone.now(),
                )
                .first()
            )
            if event is None:
                continue
            event.attempts += 1
            try:
                result = client.capture(
                    event.event,
                    distinct_id=event.distinct_id,
                    properties=event.properties,
                    timestamp=event.occurred_at,
                    uuid=str(event.pk),
                    options={'process_person_profile': event.properties.get('auth_state') == 'authenticated'},
                )
                if not result:
                    raise RuntimeError('Analytics event was not acknowledged')
                event.delivered_at = timezone.now()
                delivered += 1
            except Exception:
                # No payload or identity in failure logs. The original timestamp/UUID survive retry.
                logger.warning('Analytics delivery failed for outbox event %s', event.pk)
                event.next_attempt_at = timezone.now() + timedelta(seconds=min(3600, 15 * 2 ** min(event.attempts, 8)))
            event.save(update_fields=['attempts', 'delivered_at', 'next_attempt_at'])
    return delivered
