from django.db import models
from django.utils.translation import gettext_lazy as _

from .block import Block


class WireType(models.TextChoices):
    DEPOSIT = 'DEPOSIT', _('Deposit')
    WITHDRAW = 'WITHDRAW', _('Withdraw')


class Wire(Block):
    core = models.ForeignKey('cores.Core', on_delete=models.CASCADE)
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    wire_type = models.CharField(choices=WireType.choices, max_length=8)

    def __str__(self):
        return (
            f'Wire ID: {self.pk} | '
            f'Owner: {self.owner.username} | '
            f'Core: {self.core.ticker} | '
            f'Amount: {self.amount}'
        )
