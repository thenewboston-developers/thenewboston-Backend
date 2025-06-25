from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import ForeignKey
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker

from thenewboston.general.clients.redis import get_redis_client
from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.models.created_modified import AdjustableTimestampsModel
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.notifications.models import Notification
from thenewboston.wallets.models import Wallet

from .asset_pair import AssetPair


class ExchangeOrderSide(models.IntegerChoices):
    BUY = 1, _('Buy')
    SELL = -1, _('Sell')


class ExchangeOrderStatus(models.IntegerChoices):
    OPEN = 1, _('Open')
    PARTIALLY_FILLED = 2, _('Partially Filled')
    FILLED = 3, _('Filled')
    CANCELLED = 100, _('Cancelled')


ORDER_PROCESSING_LOCK_ID = 1
NEW_ORDER_EVENT = 'new_order'
NON_FIELD_ERRORS = 'non_field_errors'
CHANGEABLE_FIELDS = frozenset(('status', 'filled_quantity'))
UNFILLED_STATUSES = (ExchangeOrderStatus.OPEN.value, ExchangeOrderStatus.PARTIALLY_FILLED.value)  # type: ignore
SOMEWHAT_FILLED_STATUSES = (
    ExchangeOrderStatus.PARTIALLY_FILLED.value,  # type: ignore
    ExchangeOrderStatus.FILLED.value,  # type: ignore
)
FINAL_STATUSES = (ExchangeOrderStatus.FILLED.value, ExchangeOrderStatus.CANCELLED.value)  # type: ignore


def publish_new_order_message():
    # TODO(dmu) LOW: Consider adding the serialized order data to the message. For now it is not needed
    get_redis_client().publish(settings.ORDER_PROCESSING_CHANNEL_NAME, NEW_ORDER_EVENT)


class ExchangeOrder(AdjustableTimestampsModel):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    primary_currency = ForeignKey('currencies.Currency', on_delete=models.CASCADE, related_name='primary_orders')
    secondary_currency = ForeignKey('currencies.Currency', on_delete=models.CASCADE, related_name='secondary_orders')
    side = models.SmallIntegerField(choices=ExchangeOrderSide.choices)
    quantity = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    price = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    filled_quantity = models.PositiveBigIntegerField(default=0)
    status = models.PositiveSmallIntegerField(
        choices=ExchangeOrderStatus.choices,
        default=ExchangeOrderStatus.OPEN.value  # type: ignore
    )

    tracker = FieldTracker()

    def clean_status(self):
        if (
            # We are intentionally blind to re-entering the status, assume that in the that case we are just
            # not changing the status. Otherwise, we would need to make this validation on API level which would
            # complicate the implementation without any real benefit.
            self.has_changed('status') and self.status == ExchangeOrderStatus.CANCELLED.value and
            self.tracker.previous('status') in FINAL_STATUSES
        ):
            raise ValidationError('Cannot cancel an order that is in final status.')

    def clean_filled_quantity(self):
        if self.filled_quantity > self.quantity:
            raise ValidationError('Filled quantity cannot exceed order quantity.')

    def clean(self):
        if not self.is_adding() and (changed_fields := self.changed_fields().keys() - CHANGEABLE_FIELDS):
            # An extra safety check for unsupported changes
            raise ValidationError({field_name: ['Not allowed to change.']} for field_name in changed_fields)

        if self.has_changed('primary_currency', 'secondary_currency') and not AssetPair.objects.filter(
            primary_currency=self.primary_currency,
            secondary_currency=self.secondary_currency,
        ).exists():
            raise ValidationError({
                NON_FIELD_ERRORS: ['Asset pair for the given primary and secondary currency does not exist.']
            })

    def get_pair_ids(self) -> tuple[int, int]:
        return self.primary_currency_id, self.secondary_currency_id

    @property
    def unfilled_quantity(self):
        return self.quantity - self.filled_quantity

    def fill_order(self, quantity):
        assert 0 < quantity <= self.unfilled_quantity
        self.filled_quantity += quantity

    def notify_filled(self):
        Notification(
            owner=self.owner,
            payload={
                'notification_type': NotificationType.EXCHANGE_ORDER_FILLED.value,
                'order_id': self.id,
                'side': self.side,
                'quantity': self.quantity,
                'price': self.price,
                'primary_currency_id': self.primary_currency_id,
                'primary_currency_ticker': self.primary_currency.ticker,
                'secondary_currency_id': self.secondary_currency_id,
                'secondary_currency_ticker': self.secondary_currency.ticker,
            }
        ).save(should_stream=True)

    def stream(self):
        from ..consumers.exchange_order import ExchangeOrderConsumer
        from ..serializers.exchange_order import ExchangeOrderReadSerializer

        apply_on_commit(
            lambda data=ExchangeOrderReadSerializer(self).data, primary_currency_id=self.primary_currency_id,
            secondary_currency_id=self.secondary_currency_id: ExchangeOrderConsumer.stream_exchange_order(
                message_type=MessageType.UPDATE_EXCHANGE_ORDER,
                order_data=data,
                primary_currency_id=primary_currency_id,
                secondary_currency_id=secondary_currency_id,
            )
        )

    def ensure_filled_status(self):
        if self.has_changed('filled_quantity'):
            # We purposefully change status back to PARTIALLY_FILLED or OPEN in case of `filled_quantity` reduction
            if self.unfilled_quantity <= 0:
                self.status = ExchangeOrderStatus.FILLED.value
            elif self.filled_quantity > 0:
                self.status = ExchangeOrderStatus.PARTIALLY_FILLED.value

    def get_unfilled_total_and_currency_field(self) -> tuple[int, str]:
        unfilled_quantity = self.unfilled_quantity
        if (side := self.side) == ExchangeOrderSide.BUY.value:  # type: ignore
            return unfilled_quantity * self.price, 'secondary_currency'
        else:
            assert side == ExchangeOrderSide.SELL.value  # type: ignore # defensive programming
            return unfilled_quantity, 'primary_currency'

        raise NotImplementedError(f'Unsupported order side: {side}')  # defensive programming

    def get_debit_wallet(self, currency):
        # ordering is important (!) for stable selects
        return Wallet.objects.filter(owner=self.owner, currency=currency).select_for_update().order_by('pk')

    def reserve_wallet_balance(self):
        assert not transaction.get_connection().in_atomic_block

        assert self.unfilled_quantity == self.quantity
        total, currency_field = self.get_unfilled_total_and_currency_field()
        currency = getattr(self, currency_field)
        # ordering is important (!) for stable selects
        if not (wallet := self.get_debit_wallet(currency)):
            raise ValidationError([{currency_field: [f'{currency.ticker} wallet does not exist.']}])

        if wallet and self.quantity > wallet.balance:
            raise ValidationError({NON_FIELD_ERRORS: [f'Total of {total} exceeds wallet balance of {wallet.balance}']})

        wallet.change_balance(-total)

    def cancel(self, set_status=True):
        assert not transaction.get_connection().in_atomic_block

        if set_status:
            self.status = ExchangeOrderStatus.CANCELLED.value

        refund_amount, refund_currency_field = self.get_unfilled_total_and_currency_field()
        refund_currency = getattr(self, refund_currency_field)
        wallet = self.get_debit_wallet(refund_currency)
        wallet.change_balance(refund_amount)

    def save(self, *args, change_status=True, notify_filled=True, should_adjust_timestamps=True, **kwargs):
        assert transaction.get_connection().in_atomic_block
        if change_status:
            self.ensure_filled_status()

        was_status_changed = self.has_changed('status')
        if notify_filled:
            notify_filled = was_status_changed and self.status == ExchangeOrderStatus.FILLED.value

        had_changes = self.has_changes()
        self.full_clean()
        if was_adding := self.is_adding():
            self.reserve_wallet_balance()

        rv = super().save(*args, should_adjust_timestamps=should_adjust_timestamps, **kwargs)

        if was_status_changed and self.status == ExchangeOrderStatus.CANCELLED.value:
            self.cancel(set_status=False)  # we already have the status

        if was_adding:
            apply_on_commit(publish_new_order_message)

        if had_changes:
            self.stream()

        if notify_filled:
            # TODO(dmu) MEDIUM: Do we really need to notify about order being filled since we are already streaming?
            self.notify_filled()

        return rv  # return value for forward compatibility

    def __str__(self):
        return (
            f'{self.pk} | '
            f'{self.get_order_direction_display()} | '
            f'{self.quantity} {self.primary_currency.ticker} | '
            f'{self.price} {self.secondary_currency.ticker} | '
            f'{self.get_fill_status_display()}'
        )
