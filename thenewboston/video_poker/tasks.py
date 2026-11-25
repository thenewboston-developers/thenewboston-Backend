import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from thenewboston.casino.models import CasinoBet

from .engine import TIMEOUT_SECONDS
from .services import GAME, expire_hand

logger = logging.getLogger(__name__)


@shared_task(name='tasks.expire_video_poker_hands')
def expire_video_poker_hands():
    candidates = (
        CasinoBet.objects.filter(
            game=GAME, status='open', created_date__lte=timezone.now() - timedelta(seconds=TIMEOUT_SECONDS)
        )
        .order_by('id')
        .values_list('id', flat=True)[:100]
    )
    settled = 0
    for bet_id in list(candidates):
        try:
            settled += expire_hand(bet_id=bet_id).status == 'settled'
        except Exception:
            logger.exception('Video Poker hand %s timeout failed; reservation retained', bet_id)
    return {'settled': settled}
