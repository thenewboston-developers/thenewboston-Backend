import time
from datetime import datetime, timedelta, timezone

import pytest

from thenewboston.exchange.models import ExchangeOrder
from thenewboston.exchange.order_processing.engine import get_potentially_matching_orders

from .factories.exchange_order import make_buy_order, make_sell_order


@pytest.fixture
def trade_at():
    # Fake trade_at into the future, so all orders created in test included
    return datetime.now(timezone.utc) + timedelta(hours=1)


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__matching_by_price_exactly(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency
):
    assert not ExchangeOrder.objects.exists()
    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)
    assert get_potentially_matching_orders(trade_at) == [sell_order, buy_order]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__matching_by_price_with_gap(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency
):
    assert not ExchangeOrder.objects.exists()
    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=101)
    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)
    assert get_potentially_matching_orders(trade_at) == [sell_order, buy_order]


@pytest.mark.django_db
def test_get_potentially_matching_orders__no_orders(trade_at):
    assert not ExchangeOrder.objects.exists()
    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet')
def test_get_potentially_matching_orders__one_buy_order(trade_at, bucky, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_tnb_wallet')
def test_get_potentially_matching_orders__one_sell_order(trade_at, bucky, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    make_sell_order(bucky, tnb_currency, yyy_currency, price=100)
    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__not_matching_by_price(trade_at, bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    make_buy_order(bucky, tnb_currency, yyy_currency, price=80)  # too low
    make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)
    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__past_trade_orders(trade_at, bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    trade_at = datetime.now(timezone.utc) - timedelta(hours=1)
    make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    make_sell_order(dmitry, tnb_currency, yyy_currency, price=90)
    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__buy_order_is_filled(trade_at, bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    buy_order.status = 3  # FILLED
    buy_order.save()
    make_sell_order(dmitry, tnb_currency, yyy_currency, price=90)
    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__both_orders_filled(trade_at, bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    buy_order.status = 3  # FILLED
    buy_order.save()
    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=90)
    sell_order.status = 3  # FILLED
    sell_order.save()
    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_yyy_wallet')
def test_get_potentially_matching_orders__order_currency_pairs_differ(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency, zzz_currency
):
    assert not ExchangeOrder.objects.exists()
    make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    make_sell_order(dmitry, yyy_currency, zzz_currency, price=90)
    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__sell_orders_ordered_by_price_then_created_date(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency
):
    assert not ExchangeOrder.objects.exists()

    sell_order_3 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=95)
    time.sleep(0.001)
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=90)
    assert sell_order_3.created_date < sell_order_1.created_date
    time.sleep(0.001)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=90)
    assert sell_order_1.created_date < sell_order_2.created_date
    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)

    assert get_potentially_matching_orders(trade_at) == [
        sell_order_1,
        sell_order_2,
        sell_order_3,
        buy_order,
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__buy_orders_ordered_by_price_then_created_date(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency
):
    assert not ExchangeOrder.objects.exists()
    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=90)
    buy_higher_price_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=110)
    time.sleep(0.001)
    buy_lower_price_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    assert get_potentially_matching_orders(trade_at) == [
        sell_order,
        buy_lower_price_order,
        buy_higher_price_order,  # better buy by price
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__ordering_fallback_to_id(trade_at, bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()

    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=90)
    sell_order_2 = make_sell_order(
        dmitry, tnb_currency, yyy_currency, price=90, created_date=sell_order_1.created_date
    )
    assert sell_order_1.created_date == sell_order_2.created_date
    assert sell_order_1.id < sell_order_2.id

    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)

    assert get_potentially_matching_orders(trade_at) == [
        sell_order_1,
        sell_order_2,
        buy_order,
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'bucky_zzz_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__multiple_currency_pairs(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency, zzz_currency
):
    assert not ExchangeOrder.objects.exists()
    assert yyy_currency.id < zzz_currency.id

    buy_order_tnb_yyy = make_buy_order(bucky, tnb_currency, yyy_currency, price=105)
    sell_order_tnb_yyy = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)
    buy_order_tnb_zzz = make_buy_order(bucky, tnb_currency, zzz_currency, price=200)
    sell_order_tnb_zzz = make_sell_order(dmitry, tnb_currency, zzz_currency, price=190)

    assert get_potentially_matching_orders(trade_at) == [
        sell_order_tnb_yyy, sell_order_tnb_zzz, buy_order_tnb_zzz, buy_order_tnb_yyy
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__ignore_future_orders(trade_at, bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()

    make_sell_order(dmitry, tnb_currency, yyy_currency, price=90)
    make_buy_order(bucky, tnb_currency, yyy_currency, price=100, created_date=trade_at + timedelta(minutes=5))

    assert get_potentially_matching_orders(trade_at) == []


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__matching_multiple_buys_with_single_sell(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency
):
    assert not ExchangeOrder.objects.exists()

    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=105)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=103)

    assert get_potentially_matching_orders(trade_at) == [sell_order, buy_order_2, buy_order_1]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__matching_multiple_sells_with_single_buy(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency
):
    assert not ExchangeOrder.objects.exists()

    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=105)
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=98)

    assert get_potentially_matching_orders(trade_at) == [sell_order_2, sell_order_1, buy_order]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__partially_filled_order_included(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency
):
    assert not ExchangeOrder.objects.exists()

    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=105)
    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)

    buy_order.status = 2  # PARTIALLY_FILLED
    buy_order.save()

    assert get_potentially_matching_orders(trade_at) == [sell_order, buy_order]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__time_priority(trade_at, bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()

    now = datetime.now(timezone.utc)
    sell_order_later = make_sell_order(
        dmitry, tnb_currency, yyy_currency, price=100, created_date=now - timedelta(minutes=3)
    )
    sell_order_earlier = make_sell_order(
        dmitry, tnb_currency, yyy_currency, price=100, created_date=now - timedelta(minutes=4)
    )
    buy_order_earlier = make_buy_order(
        bucky, tnb_currency, yyy_currency, price=105, created_date=now - timedelta(minutes=2)
    )
    buy_order_later = make_buy_order(
        bucky, tnb_currency, yyy_currency, price=105, created_date=now - timedelta(minutes=1)
    )

    assert get_potentially_matching_orders(trade_at) == [
        sell_order_earlier, sell_order_later, buy_order_later, buy_order_earlier
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'bucky_zzz_wallet', 'dmitry_tnb_wallet', 'dmitry_zzz_wallet')
def test_get_potentially_matching_orders__complex_realistic_scenario(
    trade_at, bucky, dmitry, tnb_currency, yyy_currency, zzz_currency
):
    assert not ExchangeOrder.objects.exists()

    # Cancelled order
    make_buy_order(bucky, tnb_currency, yyy_currency, price=105, status=100)

    # Partially filled order
    partially_filled_sell = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100, status=2)

    # Filled order
    make_buy_order(bucky, tnb_currency, yyy_currency, price=110, status=3)

    # Open buy/sell orders (matching prices)
    open_buy_matching = make_buy_order(bucky, tnb_currency, yyy_currency, price=102)
    open_sell_matching = make_sell_order(dmitry, tnb_currency, yyy_currency, price=101)

    # Open buy/sell orders (non-matching prices)
    make_buy_order(bucky, tnb_currency, yyy_currency, price=95)
    make_sell_order(dmitry, tnb_currency, yyy_currency, price=107)

    # Different currency pairs (matching)
    open_buy_matching_other_currency = make_buy_order(bucky, tnb_currency, zzz_currency, price=200)
    open_sell_matching_other_currency = make_sell_order(dmitry, tnb_currency, zzz_currency, price=199)

    # Different currency pairs (non-matching)
    make_buy_order(bucky, tnb_currency, zzz_currency, price=180)
    make_sell_order(dmitry, tnb_currency, zzz_currency, price=210)

    # Orders with future created_date (should be ignored)
    make_buy_order(bucky, tnb_currency, yyy_currency, price=103, created_date=trade_at + timedelta(minutes=5))

    # Exactly trade_at must be included
    exactly_trade_at_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=99, created_date=trade_at)

    orders = get_potentially_matching_orders(trade_at)
    assert orders == [
        exactly_trade_at_order,
        partially_filled_sell,
        open_sell_matching,
        open_sell_matching_other_currency,
        # -------------------------------
        open_buy_matching_other_currency,
        open_buy_matching,
    ]
    assert sorted(orders[:4], key=lambda x: x.price) == orders[:4]
    assert sorted(orders[-2:], key=lambda x: x.price, reverse=True) == orders[-2:]
