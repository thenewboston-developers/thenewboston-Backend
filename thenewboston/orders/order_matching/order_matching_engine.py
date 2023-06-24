from django.db import transaction

from thenewboston.wallets.models import Wallet

from ..models import Trade
from ..models.order import FillStatus, Order, OrderType


class OrderMatchingEngine:

    @staticmethod
    def process_buy_order(buy_order):
        primary_currency = buy_order.primary_currency
        secondary_currency = buy_order.secondary_currency

        sell_orders = Order.objects.filter(
            fill_status__in=[FillStatus.OPEN, FillStatus.PARTIALLY_FILLED],
            order_type=OrderType.SELL,
            price__lte=buy_order.price,
            primary_currency=primary_currency,
            secondary_currency=secondary_currency,
        ).order_by('price')

        for sell_order in sell_orders:
            buy_order_remaining = buy_order.quantity - buy_order.filled_amount
            sell_order_remaining = sell_order.quantity - sell_order.filled_amount

            fill_quantity = min(buy_order_remaining, sell_order_remaining)

            buy_order.filled_amount += fill_quantity
            sell_order.filled_amount += fill_quantity

            if buy_order.filled_amount == buy_order.quantity:
                buy_order.fill_status = FillStatus.FILLED
            else:
                buy_order.fill_status = FillStatus.PARTIALLY_FILLED

            if sell_order.filled_amount == sell_order.quantity:
                sell_order.fill_status = FillStatus.FILLED
            else:
                sell_order.fill_status = FillStatus.PARTIALLY_FILLED

            Trade.objects.create(
                buy_order=buy_order,
                fill_quantity=fill_quantity,
                price=sell_order.price,
                sell_order=sell_order,
            )

            total_trade_price = fill_quantity * sell_order.price

            # Update buyer's wallet
            buyer_wallet, created = Wallet.objects.get_or_create(
                owner=buy_order.owner,
                core=primary_currency,
                defaults={'balance': fill_quantity},
            )

            if not created:
                buyer_wallet.balance += fill_quantity
                buyer_wallet.save()

            # Update seller's wallet
            seller_wallet, created = Wallet.objects.get_or_create(
                owner=sell_order.owner,
                core=secondary_currency,
                defaults={'balance': total_trade_price},
            )

            if not created:
                seller_wallet.balance += total_trade_price
                seller_wallet.save()

            buy_order.save()
            sell_order.save()

            if buy_order.fill_status == FillStatus.FILLED:
                break

    @transaction.atomic
    def process_new_order(self, new_order):
        if new_order.order_type == OrderType.BUY:
            self.process_buy_order(new_order)
        elif new_order.order_type == OrderType.SELL:
            self.process_sell_order(new_order)

    @staticmethod
    def process_sell_order(sell_order):
        primary_currency = sell_order.primary_currency
        secondary_currency = sell_order.secondary_currency

        buy_orders = Order.objects.filter(
            fill_status__in=[FillStatus.OPEN, FillStatus.PARTIALLY_FILLED],
            order_type=OrderType.BUY,
            price__gte=sell_order.price,
            primary_currency=primary_currency,
            secondary_currency=secondary_currency,
        ).order_by('-price')

        for buy_order in buy_orders:
            buy_order_remaining = buy_order.quantity - buy_order.filled_amount
            sell_order_remaining = sell_order.quantity - sell_order.filled_amount

            fill_quantity = min(buy_order_remaining, sell_order_remaining)

            buy_order.filled_amount += fill_quantity
            sell_order.filled_amount += fill_quantity

            if buy_order.filled_amount == buy_order.quantity:
                buy_order.fill_status = FillStatus.FILLED
            else:
                buy_order.fill_status = FillStatus.PARTIALLY_FILLED

            if sell_order.filled_amount == sell_order.quantity:
                sell_order.fill_status = FillStatus.FILLED
            else:
                sell_order.fill_status = FillStatus.PARTIALLY_FILLED

            Trade.objects.create(
                buy_order=buy_order,
                fill_quantity=fill_quantity,
                price=sell_order.price,
                sell_order=sell_order,
            )

            total_trade_price = fill_quantity * sell_order.price

            # Update buyer's wallet
            buyer_wallet, created = Wallet.objects.get_or_create(
                owner=buy_order.owner,
                core=secondary_currency,
                defaults={'balance': total_trade_price},
            )

            if not created:
                buyer_wallet.balance += total_trade_price
                buyer_wallet.save()

            # Update seller's wallet
            seller_wallet, created = Wallet.objects.get_or_create(
                owner=sell_order.owner,
                core=primary_currency,
                defaults={'balance': fill_quantity},
            )

            if not created:
                seller_wallet.balance += fill_quantity
                seller_wallet.save()

            buy_order.save()
            sell_order.save()

            if sell_order.fill_status == FillStatus.FILLED:
                break
