import logging
from datetime import timedelta

from django.utils import timezone

from ..models import Trade, TradeHistoryItem

UPDATE_PERIOD = timedelta(hours=24 * 7 + 1)

logger = logging.getLogger(__name__)


def update_trade_history():
    asset_pair_ids = set(TradeHistoryItem.objects.values_list('asset_pair_id', flat=True))
    asset_pair_ids |= set(
        Trade.objects.filter(
            created_date__gte=timezone.now() - UPDATE_PERIOD,
        )
        .values_list('buy_order__asset_pair_id', flat=True)
        .distinct()
    )
    try:
        # A single statement reads the trades of all currency pairs, so they all come from the same database snapshot
        TradeHistoryItem.objects.update_for_currency_pairs(asset_pair_ids)
        return
    except Exception:
        logger.warning('Error updating trade history items at once, updating them one by one', exc_info=True)

    # One currency pair that cannot be updated must not keep the others from being updated
    for asset_pair_id in asset_pair_ids:
        try:
            TradeHistoryItem.objects.update_for_currency_pair(asset_pair_id)
        except Exception:
            logger.warning('Error updating trade history items for currency pair id: %s', asset_pair_id, exc_info=True)
