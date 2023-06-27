from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from thenewboston.general.models import CreatedModified


class FillStatus(models.TextChoices):
    OPEN = 'OPEN', _('Open')
    PARTIALLY_FILLED = 'PARTIALLY_FILLED', _('Partially Filled')
    FILLED = 'FILLED', _('Filled')
    CANCELLED = 'CANCELLED', _('Cancelled')


class OrderType(models.TextChoices):
    BUY = 'BUY', _('Buy')
    SELL = 'SELL', _('Sell')


class Order(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    primary_currency = models.ForeignKey('cores.Core', on_delete=models.CASCADE, related_name='primary_orders')
    secondary_currency = models.ForeignKey('cores.Core', on_delete=models.CASCADE, related_name='secondary_orders')
    order_type = models.CharField(choices=OrderType.choices, max_length=4)
    quantity = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    price = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    filled_amount = models.PositiveBigIntegerField(default=0)
    fill_status = models.CharField(choices=FillStatus.choices, default=FillStatus.OPEN, max_length=16)

    def __str__(self):
        return (
            f'{self.order_type} | '
            f'{self.quantity} {self.primary_currency.ticker} | '
            f'{self.price} {self.secondary_currency.ticker} | '
            f'{self.fill_status}'
        )
