from django.db import models

from thenewboston.general.constants import ACCOUNT_NUMBER_LENGTH, SIGNING_KEY_LENGTH
from thenewboston.general.managers import CustomManager, CustomQuerySet
from thenewboston.general.models import CreatedModified
from thenewboston.general.utils.cryptography import generate_key_pair
from thenewboston.general.validators import HexStringValidator


class WalletQuerySet(CustomQuerySet):

    def get_or_create(self, defaults=None, **kwargs):
        # TODO(dmu) MEDIUM: Consider overriding create() as well
        defaults = defaults.copy() if defaults else {}
        if 'deposit_account_number' not in defaults and 'deposit_account_number' not in kwargs:
            assert 'deposit_signing_key' not in defaults
            assert 'deposit_signing_key' not in kwargs

            key_pair = generate_key_pair()
            defaults['deposit_account_number'] = key_pair.public
            defaults['deposit_signing_key'] = key_pair.private
        else:
            assert 'deposit_signing_key' in defaults or 'deposit_signing_key' in kwargs

        return super().get_or_create(defaults=defaults, **kwargs)


class WalletManager(CustomManager.from_queryset(WalletQuerySet)):  # type: ignore
    pass


class Wallet(CreatedModified):

    objects = WalletManager()

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
