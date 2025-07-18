from model_bakery import baker

from thenewboston.exchange.models.exchange_order import ExchangeOrderSide

# TODO(dmu) MEDIUM: Move this to factories


def make_order(owner, side, primary_currency, secondary_currency, quantity=1, price=1, created_date=None, status=None):
    kwargs = {'created_date': created_date} if created_date else {}
    if status is not None:
        kwargs['status'] = status

    return baker.make(
        'exchange.ExchangeOrder',
        owner=owner,
        side=side,
        primary_currency=primary_currency,
        secondary_currency=secondary_currency,
        quantity=quantity,
        price=price,
        **kwargs,
    )


def make_sell_order(owner, primary_currency, secondary_currency, quantity=1, price=1, created_date=None, status=None):
    return make_order(
        owner,
        ExchangeOrderSide.SELL.value,
        primary_currency,
        secondary_currency,
        quantity,
        price,
        created_date=created_date,
        status=status,
    )


def make_buy_order(owner, primary_currency, secondary_currency, quantity=1, price=1, created_date=None, status=None):
    return make_order(
        owner,
        ExchangeOrderSide.BUY.value,
        primary_currency,
        secondary_currency,
        quantity,
        price,
        created_date=created_date,
        status=status,
    )
