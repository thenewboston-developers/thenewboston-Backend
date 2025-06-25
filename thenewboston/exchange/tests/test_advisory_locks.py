import pytest
from django.test import override_settings
from django.utils import timezone

from thenewboston.exchange.models import ExchangeOrder
from thenewboston.exchange.models.exchange_order import ORDER_PROCESSING_LOCK_ID
from thenewboston.exchange.order_processing.engine import (
    get_potentially_matching_orders, match_orders, run_single_iteration
)

from .base import has_advisory_locks, is_advisory_lock_set
from .factories.exchange_order import make_buy_order, make_sell_order


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_potentially_matching_orders__matching_by_price_exactly(bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=99)
    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)
    assert get_potentially_matching_orders() == [sell_order, buy_order_1]

    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, sell_order.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order_1.id)
    assert not is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order_2.id)


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_order_update_creates_advisory_lock(authenticated_api_client, bucky, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    response = authenticated_api_client.patch(f'/api/exchange-orders/{buy_order.id}', {'status': 100})
    assert (response.status_code, response.json()) == (
        200, {
            'primary_currency': buy_order.primary_currency_id,
            'secondary_currency': buy_order.secondary_currency_id,
            'side': 1,
            'quantity': 1,
            'price': 100,
            'status': 100
        }
    )

    # Because each test opens a transaction before the API request the lock is not released
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order.id)


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
@pytest.mark.usefixtures('lock_order_processing')
def test_advisory_lock_are_cleaned_up(bucky, dmitry, tnb_currency, yyy_currency):
    # More buy orders than sell orders
    assert not ExchangeOrder.objects.exists()
    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=10)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=10)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=11)
    buy_order_3 = make_buy_order(bucky, tnb_currency, yyy_currency, price=12)
    for _ in ExchangeOrder.objects.with_advisory_lock(ORDER_PROCESSING_LOCK_ID):
        pass

    match_orders([sell_order, buy_order_1, buy_order_2, buy_order_3], timezone.now())
    assert not has_advisory_locks()
    ExchangeOrder.objects.all().delete()

    # More sell orders than buy orders
    assert not ExchangeOrder.objects.exists()
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=10)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=9)
    sell_order_3 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=8)
    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=10)
    for _ in ExchangeOrder.objects.with_advisory_lock(ORDER_PROCESSING_LOCK_ID):
        pass

    match_orders([sell_order_3, sell_order_2, sell_order_1, buy_order], timezone.now())
    assert not has_advisory_locks()
    ExchangeOrder.objects.all().delete()

    # Some buy and some sell order left after matching (the advisory locks stay)
    assert not ExchangeOrder.objects.exists()
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=10)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=9)
    sell_order_3 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=8)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=10)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=11)
    for _ in ExchangeOrder.objects.with_advisory_lock(ORDER_PROCESSING_LOCK_ID):
        pass

    with override_settings(ONE_TRADE_PER_ITERATION=True):
        match_orders([sell_order_3, sell_order_2, sell_order_1, buy_order_1, buy_order_2], timezone.now())

    sell_order_1.refresh_from_db()
    sell_order_2.refresh_from_db()
    sell_order_3.refresh_from_db()
    buy_order_1.refresh_from_db()
    buy_order_2.refresh_from_db()

    assert sell_order_3.status == 3  # FILLED
    assert sell_order_2.status == 1
    assert sell_order_1.status == 1
    assert buy_order_1.status == 1
    assert buy_order_2.status == 3  # FILLED

    assert not is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, sell_order_3.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, sell_order_2.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, sell_order_1.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order_1.id)
    assert not is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order_2.id)
    for _ in ExchangeOrder.objects.all().with_advisory_unlock(ORDER_PROCESSING_LOCK_ID):
        pass
    ExchangeOrder.objects.all().delete()

    # Partly filled sell order stays locked
    assert not ExchangeOrder.objects.exists()
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=10)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=9, quantity=5)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=11)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=12)
    for _ in ExchangeOrder.objects.with_advisory_lock(ORDER_PROCESSING_LOCK_ID):
        pass

    with override_settings(ONE_TRADE_PER_ITERATION=True):
        match_orders([sell_order_2, sell_order_1, buy_order_1, buy_order_2], timezone.now())

    sell_order_1.refresh_from_db()
    sell_order_2.refresh_from_db()
    buy_order_1.refresh_from_db()
    buy_order_2.refresh_from_db()

    assert sell_order_2.status == 2  # PARTIALLY_FILLED
    assert sell_order_1.status == 1
    assert buy_order_1.status == 1
    assert buy_order_2.status == 3  # FILLED

    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, sell_order_2.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, sell_order_1.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order_1.id)
    assert not is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order_2.id)
    for _ in ExchangeOrder.objects.all().with_advisory_unlock(ORDER_PROCESSING_LOCK_ID):
        pass
    ExchangeOrder.objects.all().delete()

    # Partly filled buy order stays locked
    assert not ExchangeOrder.objects.exists()
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=10)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=9)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=11)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=12, quantity=5)
    for _ in ExchangeOrder.objects.with_advisory_lock(ORDER_PROCESSING_LOCK_ID):
        pass

    with override_settings(ONE_TRADE_PER_ITERATION=True):
        match_orders([sell_order_2, sell_order_1, buy_order_1, buy_order_2], timezone.now())

    sell_order_1.refresh_from_db()
    sell_order_2.refresh_from_db()
    buy_order_1.refresh_from_db()
    buy_order_2.refresh_from_db()

    assert sell_order_2.status == 3  # FILLED
    assert sell_order_1.status == 1
    assert buy_order_1.status == 1
    assert buy_order_2.status == 2  # PARTIALLY_FILLED

    assert not is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, sell_order_2.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, sell_order_1.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order_1.id)
    assert is_advisory_lock_set(ORDER_PROCESSING_LOCK_ID, buy_order_2.id)
    for _ in ExchangeOrder.objects.all().with_advisory_unlock(ORDER_PROCESSING_LOCK_ID):
        pass
    ExchangeOrder.objects.all().delete()

    # Some buy and some sell order left after matching
    assert not ExchangeOrder.objects.exists()
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=10)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=9)
    sell_order_3 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=8)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=10)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=11)
    with override_settings(ONE_TRADE_PER_ITERATION=True):
        run_single_iteration()

    sell_order_1.refresh_from_db()
    sell_order_2.refresh_from_db()
    sell_order_3.refresh_from_db()
    buy_order_1.refresh_from_db()
    buy_order_2.refresh_from_db()

    assert sell_order_3.status == 3  # FILLED
    assert sell_order_2.status == 1
    assert sell_order_1.status == 1
    assert buy_order_1.status == 1
    assert buy_order_2.status == 3  # FILLED
    assert not has_advisory_locks()
    ExchangeOrder.objects.all().delete()
