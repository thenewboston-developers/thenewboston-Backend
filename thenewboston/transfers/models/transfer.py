from django.db import models
from django.utils.translation import gettext_lazy as _

from .block import Block


class TransferType(models.TextChoices):
    DEPOSIT = 'DEPOSIT', _('Deposit')
    WITHDRAW = 'WITHDRAW', _('Withdraw')


class Transfer(Block):
    core = models.ForeignKey('cores.Core', on_delete=models.CASCADE)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    transfer_type = models.CharField(choices=TransferType.choices, max_length=8)

    def __str__(self):
        return (
            f'Transfer ID: {self.pk} | '
            f'User: {self.user.username} | '
            f'Core: {self.core.ticker} | '
            f'Amount: {self.amount}'
        )
