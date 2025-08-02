from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import transaction
from django.db.models import (
    PROTECT, ForeignKey, IntegerChoices, PositiveBigIntegerField, PositiveSmallIntegerField, SmallIntegerField
)
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker

from thenewboston.general.clients.redis import get_redis_client
from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.models.created_modified import AdjustableTimestampsModel
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.notifications.models import Notification
from thenewboston.wallets.models import Wallet


class ExchangeOrderSide(IntegerChoices):
    BUY = 1, _('Buy')
    SELL = -1, _('Sell')


class ExchangeOrderStatus(IntegerChoices):
    OPEN = 1, _('Open')
    PARTIALLY_FILLED = 2, _('Partially Filled')
    FILLED = 3, _('Filled')
    CANCELLED = 100, _('Cancelled')


ORDER_PROCESSING_LOCK_ID = 1
NEW_ORDER_EVENT = 'new_order'
# We need `modified_date` to be in `CHANGEABLE_FIELDS` to allow timestamp adjustments
CHANGEABLE_FIELDS = frozenset(('status', 'filled_quantity', 'modified_date'))  # type: ignore
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
    owner = ForeignKey('users.User', on_delete=PROTECT)
    asset_pair = ForeignKey('AssetPair', on_delete=PROTECT, related_name='exchange_orders', null=True)
    side = SmallIntegerField(choices=ExchangeOrderSide.choices)
    quantity = PositiveBigIntegerField(validators=[MinValueValidator(1)])
    price = PositiveBigIntegerField(validators=[MinValueValidator(1)])
    filled_quantity = PositiveBigIntegerField(default=0)
    status = PositiveSmallIntegerField(
        choices=ExchangeOrderStatus.choices,
        default=ExchangeOrderStatus.OPEN.value  # type: ignore
    )

    tracker = FieldTracker()

    def _clean_status(self):
        if (
            # We are intentionally blind to re-entering the status, assume that in the that case we are just
            # not changing the status. Otherwise, we would need to make this validation on API level which would
            # complicate the implementation without any real benefit.
            self.has_changed('status') and self.status == ExchangeOrderStatus.CANCELLED.value and
            self.tracker.previous('status') in FINAL_STATUSES
        ):
            # TODO(dmu) HIGH: Implement a true state machine, so only particular transitions are allowed
            raise ValidationError({'status': 'Cannot cancel an order that is in final status.'})

    def _clean_filled_quantity(self):
        if self.filled_quantity > self.quantity:
            raise ValidationError('Filled quantity cannot exceed order quantity.')

    def _clean_wallet_balance_for_reservation(self):
        total, currency_field = self.get_unfilled_total_and_currency_field()
        currency = getattr(self.asset_pair, currency_field)
        if not (wallet := self.get_debit_wallet(currency)):
            raise ValidationError([{currency_field: [f'{currency.ticker} wallet does not exist.']}])

        if total > wallet.balance:
            # TODO(dmu) MEDIUM: Consider relying on `Wallet.change_balance` to raise an error
            raise ValidationError(
                f'Total of {total} exceeds {wallet.currency.ticker} wallet balance of {wallet.balance}'
            )

    def clean(self):
        if not self.is_adding() and (changed_fields := self.changed_fields().keys() - CHANGEABLE_FIELDS):
            # An extra safety check for unsupported changes
            raise ValidationError({field_name: ['Not allowed to change.'] for field_name in changed_fields})

        self._clean_filled_quantity()
        self._clean_status()

        if self.is_adding():
            self._clean_wallet_balance_for_reservation()

    @property
    def unfilled_quantity(self):
        return self.quantity - self.filled_quantity

    def fill_order(self, quantity):
        assert 0 < quantity <= self.unfilled_quantity
        self.filled_quantity += quantity
        self.ensure_filled_status()

    def notify_filled(self):
        asset_pair = self.asset_pair
        Notification(
            owner=self.owner,
            payload={
                'notification_type': NotificationType.EXCHANGE_ORDER_FILLED.value,
                'order_id': self.id,
                'side': self.side,
                'quantity': self.quantity,
                'price': self.price,
                'primary_currency_id': asset_pair.primary_currency_id,
                'primary_currency_ticker': asset_pair.primary_currency.ticker,
                'secondary_currency_id': asset_pair.secondary_currency_id,
                'secondary_currency_ticker': asset_pair.secondary_currency.ticker,
            }
        ).save(should_stream=True)

    def stream(self):
        from ..consumers.exchange_order import ExchangeOrderConsumer
        from ..serializers.exchange_order import ExchangeOrderReadSerializer

        asset_pair = self.asset_pair
        apply_on_commit(
            lambda order=self, primary_currency_id=asset_pair.primary_currency_id, secondary_currency_id=asset_pair.
            secondary_currency_id: ExchangeOrderConsumer.stream_exchange_order(
                message_type=MessageType.UPDATE_EXCHANGE_ORDER,
                order_data=ExchangeOrderReadSerializer(order).data,
                # TODO(dmu) LOW: Refactor, so we pass the order to stream_exchange_order() which is used to
                #                extract `primary_currency_id` and `secondary_currency_id` and then serialized
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

        assert side == ExchangeOrderSide.SELL.value  # type: ignore # defensive programming
        return unfilled_quantity, 'primary_currency'

    def get_debit_wallet(self, currency):
        return Wallet.objects.filter(owner=self.owner, currency=currency).select_for_update().get_or_none()

    def handle_cancel(self):
        assert transaction.get_connection().in_atomic_block
        assert self.status == ExchangeOrderStatus.CANCELLED.value
        refund_amount, refund_currency_field = self.get_unfilled_total_and_currency_field()
        wallet = self.get_debit_wallet(getattr(self.asset_pair, refund_currency_field))
        wallet.change_balance(refund_amount)

    def cancel(self):
        self.status = ExchangeOrderStatus.CANCELLED.value
        self.save()

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
            assert self.unfilled_quantity == self.quantity

            total, currency_field = self.get_unfilled_total_and_currency_field()
            wallet = self.get_debit_wallet(getattr(self.asset_pair, currency_field))

            # We just assert assuming the `._clean_wallet_balance_for_reservation()` has been called before
            assert wallet
            assert total <= wallet.balance

            wallet.change_balance(-total)

        rv = super().save(*args, should_adjust_timestamps=should_adjust_timestamps, **kwargs)

        if was_status_changed and self.status == ExchangeOrderStatus.CANCELLED.value:
            self.handle_cancel()  # we already have the status

        if was_adding:
            apply_on_commit(publish_new_order_message)

        if had_changes:
            self.stream()  # TODO(dmu) MEDIUM: Should we stream on order creation?

        if notify_filled:
            # TODO(dmu) MEDIUM: Do we really need to notify about order being filled since we are already streaming?
            self.notify_filled()

        return rv  # return value for forward compatibility

    def __str__(self):
        asset_pair = self.asset_pair
        return (
            f'{self.pk} | '
            f'{self.get_side_display()} | '
            f'{self.quantity} {asset_pair.primary_currency.ticker} | '
            f'{self.price} {asset_pair.secondary_currency.ticker} | '
            f'{self.get_status_display()}'
        )
