from django.db import models

from thenewboston.general.enums import MessageType
from thenewboston.general.models.created_modified import AdjustableTimestampsModel
from thenewboston.general.utils.database import apply_on_commit


class Trade(AdjustableTimestampsModel):
    buy_order = models.ForeignKey('exchange.ExchangeOrder', related_name='buy_trades', on_delete=models.CASCADE)
    sell_order = models.ForeignKey('exchange.ExchangeOrder', related_name='sell_trades', on_delete=models.CASCADE)
    filled_quantity = models.PositiveBigIntegerField()
    price = models.PositiveBigIntegerField()
    overpayment_amount = models.PositiveBigIntegerField()

    def __str__(self):
        return (
            f'Trade ID: {self.pk} | '
            f'Buy Order: {self.buy_order.pk} | '
            f'Sell Order: {self.sell_order.pk} | '
            f'Quantity: {self.fill_quantity} | '
            f'Trade Price: {self.trade_price} | '
            f'Overpayment Amount: {self.overpayment_amount}'
        )

    def save(self, *args, **kwargs):
        was_adding = self.is_adding()
        rv = super().save(*args, **kwargs)

        if was_adding:
            from ..consumers.trade import TradeConsumer
            from ..serializers.trade import TradeSerializer

            apply_on_commit(
                lambda data=TradeSerializer(self).data, ticker=self.sell_order.primary_currency.ticker: TradeConsumer.
                stream_trade(message_type=MessageType.CREATE_TRADE, trade_data=data, ticker=ticker)
            )

        return rv  # return value for forward compatibility
