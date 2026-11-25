import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import CasinoBet, CasinoCommitment
from .rules import RULES
from .services import reconcile_fund, settle_bet

logger = logging.getLogger(__name__)


@shared_task(name='tasks.reconcile_casino')
def reconcile_casino():
    # Instant games commit placement and settlement together. This only recovers exceptional persisted open bets.
    candidates = list(
        CasinoBet.objects.filter(status='open', created_date__lt=timezone.now() - timedelta(seconds=30))
        .order_by('id')
        .values_list('id', flat=True)[:100]
    )
    for bet_id in candidates:
        candidate = CasinoBet.objects.only('game', 'rules_version').get(pk=bet_id)
        rules = RULES.get((candidate.game, candidate.rules_version))
        if rules is None or rules.settlement_mode != 'instant':
            continue
        try:
            settle_bet(bet_id=bet_id)
        except Exception:
            logger.exception('Casino bet %s recovery failed; reservation retained', bet_id)
    result = reconcile_fund()
    # Never remove used commitments or financial history.
    CasinoCommitment.objects.filter(used_at__isnull=True, expires_at__lt=timezone.now() - timedelta(days=1)).delete()
    return result
