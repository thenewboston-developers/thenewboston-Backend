import logging

from django.db import transaction

from thenewboston.project.celery import app

from .models import HexMatch
from .services import advance_deadlines, queue_computer, run_computer

logger = logging.getLogger(__name__)


@app.task(name='tasks.play_hex_computer_turn', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def play_computer_turn(match_id, expected_version):
    run_computer(match_id, expected_version)


@app.task(name='tasks.sweep_hex_matches')
def sweep_hex_matches():
    ids = HexMatch.objects.filter(status__in=['pending', 'active']).values_list('id', flat=True)
    for match_id in ids.iterator():
        try:
            with transaction.atomic():
                match = HexMatch.objects.select_for_update().get(pk=match_id)
                if not advance_deadlines(match):
                    queue_computer(match)
        except Exception:
            # A failed match must not prevent other clocks, refunds, or computer retries.
            logger.exception('Could not sweep hex match %s', match_id)
