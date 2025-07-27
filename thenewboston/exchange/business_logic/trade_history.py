import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import Trade, TradeHistoryItem

UPDATE_PERIOD = timedelta(hours=24 * 7 + 1)

logger = logging.getLogger(__name__)


def update_trade_history():
    currency_pairs = set(TradeHistoryItem.objects.values_list('primary_currency_id', 'secondary_currency_id'))
    currency_pairs |= set(
        Trade.objects.filter(created_date__gte=timezone.now() - UPDATE_PERIOD,
                             ).values_list('buy_order__primary_currency_id',
                                           'buy_order__secondary_currency_id').distinct()
    )

    for primary_currency_id, secondary_currency_id in currency_pairs:
        try:
            with transaction.atomic():
                # We purposefully use transaction per currency pair because we have READ COMMITTED isolation level away
                # which still does not let us have the entire table built from instant database snapshot.
                TradeHistoryItem.objects.update_for_currency_pair(primary_currency_id, secondary_currency_id)
        except Exception:
            logger.warning(
                'Error updating trade history items for currency pair %s:%s', primary_currency_id,
                secondary_currency_id
            )
