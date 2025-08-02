import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import Trade, TradeHistoryItem

UPDATE_PERIOD = timedelta(hours=24 * 7 + 1)

logger = logging.getLogger(__name__)


def update_trade_history():
    asset_pair_ids = set(TradeHistoryItem.objects.values_list('asset_pair_id', flat=True))
    asset_pair_ids |= set(
        Trade.objects.filter(created_date__gte=timezone.now() -
                             UPDATE_PERIOD,).values_list('buy_order__asset_pair_id', flat=True).distinct()
    )
    for asset_pair_id in asset_pair_ids:
        try:
            with transaction.atomic():
                # We purposefully use transaction per currency pair because we have READ COMMITTED isolation level away
                # which still does not let us have the entire table built from instant database snapshot.
                TradeHistoryItem.objects.update_for_currency_pair(asset_pair_id)
        except Exception:
            logger.warning('Error updating trade history items for currency pair id: %s', asset_pair_id, exc_info=True)
