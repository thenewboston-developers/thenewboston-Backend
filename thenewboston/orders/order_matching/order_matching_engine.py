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

            total_trade_price = fill_quantity * sell_order.price

            print(f'Total trade price: {total_trade_price}')
            # TODO: create trade object
            print(f'Buyer receives: {fill_quantity} {primary_currency.ticker}')
            print(f'Seller receives: {total_trade_price} {secondary_currency.ticker}')

            buy_order.save()
            sell_order.save()

            if buy_order.fill_status == FillStatus.FILLED:
                break

    def process_new_order(self, new_order):
        if new_order.order_type == OrderType.BUY:
            self.process_buy_order(new_order)
        elif new_order.order_type == OrderType.SELL:
            # TODO: Complete this
            print(new_order)
