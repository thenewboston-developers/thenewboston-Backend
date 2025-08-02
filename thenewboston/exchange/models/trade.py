import logging

from django.db import models
from model_utils import FieldTracker

from thenewboston.exchange.tasks import update_trade_history_for_currency_pair_task
from thenewboston.general.enums import MessageType
from thenewboston.general.managers import CustomManager, CustomQuerySet
from thenewboston.general.models.created_modified import AdjustableTimestampsModel
from thenewboston.general.utils.celery import run_task_on_commit
from thenewboston.general.utils.database import apply_on_commit

logger = logging.getLogger(__name__)


class TradeQuerySet(CustomQuerySet):

    def filter_by_asset_pair(self, asset_pair_id):
        # TODO(dmu) LOW: We can optimize performance by storing the asset pair in the Trade model
        return self.filter(buy_order__asset_pair_id=asset_pair_id)


class TradeManager(CustomManager.from_queryset(TradeQuerySet)):  # type: ignore
    pass


class Trade(AdjustableTimestampsModel):
    # TODO(dmu) HIGH: Consider not allowing order deletion if there were traded
    buy_order = models.ForeignKey('exchange.ExchangeOrder', related_name='buy_trades', on_delete=models.CASCADE)
    sell_order = models.ForeignKey('exchange.ExchangeOrder', related_name='sell_trades', on_delete=models.CASCADE)
    filled_quantity = models.PositiveBigIntegerField()
    price = models.PositiveBigIntegerField()
    overpayment_amount = models.PositiveBigIntegerField()

    objects = TradeManager()
    tracker = FieldTracker()

    def __str__(self):
        return (
            f'Trade ID: {self.pk} | '
            f'Buy Order: {self.buy_order.pk} | '
            f'Sell Order: {self.sell_order.pk} | '
            f'Quantity: {self.filled_quantity} | '
            f'Trade Price: {self.price} | '
            f'Overpayment Amount: {self.overpayment_amount}'
        )

    def save(self, *args, **kwargs):
        # In most cases we do not need to adjust timestamps for trades, because they are the origin of trade time
        kwargs.setdefault('should_adjust_timestamps', False)
        was_adding = self.is_adding()
        rv = super().save(*args, **kwargs)

        if was_adding:
            from ..consumers.trade import TradeConsumer
            from ..serializers.trade import TradeSerializer

            buy_order = self.buy_order
            run_task_on_commit(update_trade_history_for_currency_pair_task, asset_pair_id=buy_order.asset_pair_id)
            apply_on_commit(
                # TODO(dmu) LOW: Add comment explaining why `self.sell_order.asset_pair.primary_currency` ticker
                #                is used not, but not `self.buy_order.asset_pair.primary_currency`
                lambda trade=self, ticker=self.sell_order.asset_pair.primary_currency.ticker: TradeConsumer.
                stream_trade(
                    message_type=MessageType.CREATE_TRADE, trade_data=TradeSerializer(trade).data, ticker=ticker
                )
            )

        return rv  # return value for forward compatibility
