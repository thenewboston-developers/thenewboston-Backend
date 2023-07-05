from django.db import models

from thenewboston.general.constants import ACCOUNT_NUMBER_LENGTH, SIGNING_KEY_LENGTH
from thenewboston.general.models import CreatedModified
from thenewboston.general.validators import HexStringValidator


class Wallet(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    core = models.ForeignKey('cores.Core', on_delete=models.CASCADE)
    balance = models.PositiveBigIntegerField(default=0)
    deposit_account_number = models.CharField(
        max_length=ACCOUNT_NUMBER_LENGTH, validators=(HexStringValidator(ACCOUNT_NUMBER_LENGTH),)
    )
    deposit_balance = models.PositiveBigIntegerField(default=0)
    deposit_signing_key = models.CharField(
        max_length=SIGNING_KEY_LENGTH, validators=(HexStringValidator(SIGNING_KEY_LENGTH),)
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'core'], name='unique_owner_core')]

    def __str__(self):
        return (
            f'Wallet ID: {self.pk} | '
            f'Owner: {self.owner.username} | '
            f'Core: {self.core.ticker} | '
            f'Balance: {self.balance}'
        )
