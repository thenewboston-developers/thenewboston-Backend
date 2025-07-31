from django.core.exceptions import ValidationError
from django.db import models
from model_utils import FieldTracker

from thenewboston.general.constants import ACCOUNT_NUMBER_LENGTH, SIGNING_KEY_LENGTH
from thenewboston.general.enums import MessageType
from thenewboston.general.managers import CustomManager, CustomQuerySet
from thenewboston.general.models.created_modified import AdjustableTimestampsModel
from thenewboston.general.utils.cryptography import generate_key_pair
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.general.validators import HexStringValidator


class WalletQuerySet(CustomQuerySet):

    def get_or_create(self, defaults=None, _for_update=False, **kwargs):
        # TODO(dmu) MEDIUM: Consider overriding create() as well
        defaults = defaults.copy() if defaults else {}

        # Check if currency is provided to determine if we need deposit keys
        currency = kwargs.get('currency') or defaults.get('currency')

        if currency and currency.domain:
            # External currency - generate deposit keys if not provided
            if 'deposit_account_number' not in defaults and 'deposit_account_number' not in kwargs:
                assert 'deposit_signing_key' not in defaults
                assert 'deposit_signing_key' not in kwargs

                key_pair = generate_key_pair()
                defaults['deposit_account_number'] = key_pair.public
                defaults['deposit_signing_key'] = key_pair.private
            else:
                assert 'deposit_signing_key' in defaults or 'deposit_signing_key' in kwargs
        else:
            # Internal currency - ensure deposit fields are None
            defaults['deposit_account_number'] = None
            defaults['deposit_signing_key'] = None
            defaults['deposit_balance'] = None

        qs = self
        if _for_update:
            qs = qs.select_for_update()

        return super(WalletQuerySet, qs).get_or_create(defaults=defaults, **kwargs)


class WalletManager(CustomManager.from_queryset(WalletQuerySet)):  # type: ignore
    pass


class Wallet(AdjustableTimestampsModel):

    # TODO(dmu) HIGH: Make sure balance update always uses select from update
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    currency = models.ForeignKey('currencies.Currency', on_delete=models.CASCADE)
    balance = models.PositiveBigIntegerField(default=0)
    deposit_account_number = models.CharField(
        max_length=ACCOUNT_NUMBER_LENGTH,
        validators=(HexStringValidator(ACCOUNT_NUMBER_LENGTH),),
        null=True,
        blank=True
    )
    deposit_balance = models.PositiveBigIntegerField(default=0, null=True, blank=True)
    deposit_signing_key = models.CharField(
        max_length=SIGNING_KEY_LENGTH, validators=(HexStringValidator(SIGNING_KEY_LENGTH),), null=True, blank=True
    )

    objects = WalletManager()
    tracker = FieldTracker()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'currency'], name='unique_owner_currency')]

    def __str__(self):
        return (
            f'Wallet ID: {self.pk} | '
            f'Owner: {self.owner.username} | '
            f'Currency: {self.currency.ticker} | '
            f'Balance: {self.balance}'
        )

    def change_balance(self, amount_delta, save=True, should_stream=True, should_adjust_timestamps=True):
        if (new_balance := self.balance + amount_delta) < 0:
            # this error message should be vague to be compatible with general context
            raise ValidationError('Not enough wallet balance')
        self.balance = new_balance
        if save:
            self.save(should_stream=should_stream, should_adjust_timestamps=should_adjust_timestamps)

    def stream(self):
        from ..consumers import WalletConsumer
        from ..serializers.wallet import WalletReadSerializer

        apply_on_commit(
            lambda wallet=self: WalletConsumer.
            stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=WalletReadSerializer(wallet).data)
        )

    def _adjust_timestamps(self, was_adding, had_changes):
        if was_adding and self.created_date is not None and self.modified_date is not None:
            return  # `created_date` and `modified_date` are provided explicitly, we assume adjustment is not needed

        return super()._adjust_timestamps(was_adding, had_changes)  # return for forward compatibility

    def save(self, *args, should_stream=False, should_adjust_timestamps=True, **kwargs):
        has_balance_changed = self.has_changed('balance')
        rv = super().save(*args, should_adjust_timestamps=should_adjust_timestamps, **kwargs)

        if has_balance_changed and should_stream:
            # TODO(dmu) HIGH: Rely on this code everywhere, remove `should_stream` argument and related code
            #                 Maybe we should stream in case of changes of other fields as well?
            self.stream()  # !!! Important to stream after save, so we get correct `.pk` and `.modified_date`

        return rv  # return value for forward compatibility
