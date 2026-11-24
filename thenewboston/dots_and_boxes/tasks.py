import logging

from django.db import transaction

from thenewboston.project.celery import app

from .models import DotsAndBoxesMatch
from .services import advance_deadlines, queue_computer, run_computer

logger = logging.getLogger(__name__)


@app.task(name='tasks.play_dots_and_boxes_computer_turn', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def play_computer_turn(match_id, expected_version):
    run_computer(match_id, expected_version)


@app.task(name='tasks.sweep_dots_and_boxes_matches')
def sweep_dots_and_boxes_matches():
    ids = DotsAndBoxesMatch.objects.filter(status__in=['pending', 'active']).values_list('id', flat=True)
    for match_id in ids.iterator():
        try:
            with transaction.atomic():
                match = DotsAndBoxesMatch.objects.select_for_update().get(pk=match_id)
                if not advance_deadlines(match):
                    queue_computer(match)
        except Exception:
            # A failed match must not prevent other clocks, refunds, or computer retries.
            logger.exception('Could not sweep dots and boxes match %s', match_id)
