from django.db import transaction

from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.utils.cryptography import generate_key_pair
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.notifications.models import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.wallets.consumers import WalletConsumer
from thenewboston.wallets.models import Wallet
from thenewboston.wallets.serializers.wallet import WalletReadSerializer

from ..consumers import ExchangeOrderConsumer, TradeConsumer
from ..models import Trade
from ..models.exchange_order import ExchangeOrder, ExchangeOrderType, FillStatus
from ..serializers.exchange_order import ExchangeOrderReadSerializer
from ..serializers.trade import TradeSerializer

UNFILLED_STATUSES = (FillStatus.OPEN, FillStatus.PARTIALLY_FILLED)


class OrderMatchingEngine:

    @staticmethod
    def notify_order_filled(order, request):
        notification = Notification.objects.create(
            owner=order.owner,
            payload={
                'notification_type': NotificationType.EXCHANGE_ORDER_FILLED.value,
                'order_type': order.order_type,
                'quantity': order.quantity,
                'price': order.price,
                'primary_currency_id': order.primary_currency.id,
                'primary_currency_ticker': order.primary_currency.ticker,
                'secondary_currency_id': order.secondary_currency.id,
                'secondary_currency_ticker': order.secondary_currency.ticker,
                'order_id': order.id,
            }
        )

        notification_data = NotificationReadSerializer(notification, context={'request': request}).data

        apply_on_commit(
            lambda nd=notification_data: NotificationConsumer.
            stream_notification(message_type=MessageType.CREATE_NOTIFICATION, notification_data=nd)
        )

    @transaction.atomic
    def process_new_order(self, order, request):
        # TODO(dmu) MEDIUM: process_new_order() seems excessive, we can just use self.process_order()
        self.process_order(order, is_buy_order=order.order_type == ExchangeOrderType.BUY, request=request)

    @classmethod
    def process_order(cls, order, is_buy_order, request):
        primary_currency = order.primary_currency
        secondary_currency = order.secondary_currency

        # Choose the order type, price operator, and order_by argument based on whether it's a buy or sell order
        if is_buy_order:
            order_type = ExchangeOrderType.SELL
            price_lookup = '__lte'
            ordering_direction = ''
        else:
            order_type = ExchangeOrderType.BUY
            price_lookup = '__gte'
            ordering_direction = '-'

        # Create a dynamic filter
        matching_orders = ExchangeOrder.objects.filter(
            order_type=order_type,
            fill_status__in=UNFILLED_STATUSES,
            primary_currency=primary_currency,
            secondary_currency=secondary_currency,
            **{
                f'price{price_lookup}': order.price
            },
        ).order_by(f'{ordering_direction}price')

        for matching_order in matching_orders:
            fill_quantity = min(
                order.quantity - order.filled_amount,
                matching_order.quantity - matching_order.filled_amount,
            )

            order.filled_amount += fill_quantity
            matching_order.filled_amount += fill_quantity

            # Update the order and matching order's status
            order_was_open = order.fill_status != FillStatus.FILLED
            matching_order_was_open = matching_order.fill_status != FillStatus.FILLED

            cls.update_order_status(order)
            cls.update_order_status(matching_order)

            # Send notifications if orders were just filled
            if order_was_open and order.fill_status == FillStatus.FILLED:
                cls.notify_order_filled(order, request)

            if matching_order_was_open and matching_order.fill_status == FillStatus.FILLED:
                cls.notify_order_filled(matching_order, request)

            trade_price = min(order.price, matching_order.price)
            total_trade_price = trade_price * fill_quantity
            overpayment_amount = abs(order.price - matching_order.price) * fill_quantity

            # Create a trade object
            buy_order, sell_order = (order, matching_order) if is_buy_order else (matching_order, order)
            trade = Trade.objects.create(
                buy_order=buy_order,
                sell_order=sell_order,
                fill_quantity=fill_quantity,
                trade_price=trade_price,
                overpayment_amount=overpayment_amount,
            )

            # Broadcast the trade event
            apply_on_commit(
                lambda trade_data=TradeSerializer(trade).data, ticker=primary_currency.ticker: TradeConsumer.
                stream_trade(message_type=MessageType.CREATE_TRADE, trade_data=trade_data, ticker=ticker)
            )

            # Update the wallets of the order and matching order's owners
            cls.update_wallet(
                owner=order.owner,
                currency=primary_currency if is_buy_order else secondary_currency,
                amount=fill_quantity if is_buy_order else total_trade_price,
                request=request,
            )

            cls.update_wallet(
                owner=matching_order.owner,
                currency=secondary_currency if is_buy_order else primary_currency,
                amount=total_trade_price if is_buy_order else fill_quantity,
                request=request,
            )

            if overpayment_amount:
                cls.update_wallet(
                    owner=order.owner if is_buy_order else matching_order.owner,
                    currency=secondary_currency,
                    amount=overpayment_amount,
                    request=request,
                )

            order.save()
            matching_order.save()

            order_data = ExchangeOrderReadSerializer(order).data
            matching_order_data = ExchangeOrderReadSerializer(matching_order).data
            ExchangeOrderConsumer.stream_exchange_order(
                message_type=MessageType.UPDATE_EXCHANGE_ORDER,
                order_data=order_data,
                primary_currency_id=order.primary_currency_id,
                secondary_currency_id=order.secondary_currency_id
            )
            ExchangeOrderConsumer.stream_exchange_order(
                message_type=MessageType.UPDATE_EXCHANGE_ORDER,
                order_data=matching_order_data,
                primary_currency_id=matching_order.primary_currency_id,
                secondary_currency_id=matching_order.secondary_currency_id
            )

            if order.fill_status == FillStatus.FILLED:
                break

    @staticmethod
    def update_order_status(order):
        order.fill_status = FillStatus.FILLED if order.filled_amount == order.quantity else FillStatus.PARTIALLY_FILLED

    @staticmethod
    def update_wallet(owner, currency, amount, request):
        key_pair = generate_key_pair()
        wallet, created = Wallet.objects.get_or_create(
            owner=owner,
            currency=currency,
            defaults={
                'balance': amount,
                'deposit_account_number': key_pair.public,
                'deposit_signing_key': key_pair.private,
            },
        )

        if not created:
            wallet.balance += amount
            wallet.save()
            wallet_data = WalletReadSerializer(wallet, context={'request': request}).data
            WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data=wallet_data)
