from model_bakery import baker

from thenewboston.exchange.models.exchange_order import ExchangeOrderSide

# TODO(dmu) MEDIUM: Move this to factories


def make_order(owner, side, primary_currency, secondary_currency, quantity=1, price=1):
    return baker.make(
        'exchange.ExchangeOrder',
        owner=owner,
        side=side,
        primary_currency=primary_currency,
        secondary_currency=secondary_currency,
        quantity=quantity,
        price=price,
    )


def make_sell_order(owner, primary_currency, secondary_currency, quantity=1, price=1):
    return make_order(owner, ExchangeOrderSide.SELL.value, primary_currency, secondary_currency, quantity, price)


def make_buy_order(owner, primary_currency, secondary_currency, quantity=1, price=1):
    return make_order(owner, ExchangeOrderSide.BUY.value, primary_currency, secondary_currency, quantity, price)
