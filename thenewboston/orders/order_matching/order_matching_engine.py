from django.db import transaction

from thenewboston.general.enums import MessageType
from thenewboston.general.utils.cryptography import generate_key_pair
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.models import Wallet

from ..models import Trade
from ..models.order import FillStatus, Order, OrderType


class OrderMatchingEngine:

    @transaction.atomic
    def process_new_order(self, new_order):
        if new_order.order_type == OrderType.BUY:
            self.process_order(new_order, is_buy_order=True)
        elif new_order.order_type == OrderType.SELL:
            self.process_order(new_order, is_buy_order=False)

    @staticmethod
    def process_order(order, is_buy_order):
        primary_currency = order.primary_currency
        secondary_currency = order.secondary_currency

        # Choose the order type, price operator, and order_by argument based on whether it's a buy or sell order
        order_type = OrderType.SELL if is_buy_order else OrderType.BUY
        price_operator = '__lte' if is_buy_order else '__gte'
        price_ordering = 'price' if is_buy_order else '-price'

        # Create a dynamic filter
        matching_orders_filter = {
            'order_type': order_type,
            'fill_status__in': [FillStatus.OPEN, FillStatus.PARTIALLY_FILLED],
            f'price{price_operator}': order.price,
            'primary_currency': primary_currency,
            'secondary_currency': secondary_currency,
        }

        matching_orders = Order.objects.filter(**matching_orders_filter).order_by(price_ordering)

        for matching_order in matching_orders:
            fill_quantity = min(
                order.quantity - order.filled_amount,
                matching_order.quantity - matching_order.filled_amount,
            )

            order.filled_amount += fill_quantity
            matching_order.filled_amount += fill_quantity

            # Update the order and matching order's status
            OrderMatchingEngine.update_order_status(order)
            OrderMatchingEngine.update_order_status(matching_order)

            trade_price = min(order.price, matching_order.price)
            total_trade_price = trade_price * fill_quantity
            overpayment_amount = abs(order.price - matching_order.price) * fill_quantity

            # Create a trade object
            Trade.objects.create(
                buy_order=order if is_buy_order else matching_order,
                sell_order=matching_order if is_buy_order else order,
                fill_quantity=fill_quantity,
                trade_price=trade_price,
                overpayment_amount=overpayment_amount,
            )

            # Update the wallets of the order and matching order's owners
            OrderMatchingEngine.update_wallet(
                owner=order.owner,
                core=primary_currency if is_buy_order else secondary_currency,
                amount=fill_quantity if is_buy_order else total_trade_price,
            )

            OrderMatchingEngine.update_wallet(
                owner=matching_order.owner,
                core=secondary_currency if is_buy_order else primary_currency,
                amount=total_trade_price if is_buy_order else fill_quantity,
            )

            if overpayment_amount:
                OrderMatchingEngine.update_wallet(
                    owner=order.owner if is_buy_order else matching_order.owner,
                    core=secondary_currency,
                    amount=overpayment_amount,
                )

            order.save()
            matching_order.save()

            if order.fill_status == FillStatus.FILLED:
                break

    @staticmethod
    def update_order_status(order):
        if order.filled_amount == order.quantity:
            order.fill_status = FillStatus.FILLED
        else:
            order.fill_status = FillStatus.PARTIALLY_FILLED

    @staticmethod
    def update_wallet(owner, core, amount):
        key_pair = generate_key_pair()

        wallet, created = Wallet.objects.get_or_create(
            owner=owner,
            core=core,
            defaults={
                'balance': amount,
                'deposit_account_number': key_pair.public,
                'deposit_signing_key': key_pair.private,
            },
        )

        if not created:
            wallet.balance += amount
            wallet.save()
            WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet=wallet)
