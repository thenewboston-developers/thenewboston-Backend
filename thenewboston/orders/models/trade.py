from django.db import models

from thenewboston.general.models import CreatedModified


class Trade(CreatedModified):
    buy_order = models.ForeignKey('orders.Order', related_name='buy_trades', on_delete=models.CASCADE)
    sell_order = models.ForeignKey('orders.Order', related_name='sell_trades', on_delete=models.CASCADE)
    fill_quantity = models.PositiveBigIntegerField()
    trade_price = models.PositiveBigIntegerField()
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
