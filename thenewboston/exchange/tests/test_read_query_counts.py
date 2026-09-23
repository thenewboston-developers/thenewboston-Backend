import pytest
from model_bakery import baker
from rest_framework.test import APIRequestFactory, force_authenticate

from thenewboston.connect_five.models import ConnectFiveStats
from thenewboston.exchange.models import AssetPair, ExchangeOrder
from thenewboston.exchange.views.asset_pair import AssetPairViewSet
from thenewboston.exchange.views.exchange_order import ExchangeOrderViewSet

from .factories.exchange_order import make_buy_order, make_sell_order


@pytest.mark.django_db
@pytest.mark.parametrize('pair_count', [1, 5])
def test_asset_pair_list_has_constant_queries(django_assert_num_queries, bucky, dmitry, tnb_currency, pair_count):
    ConnectFiveStats.objects.create(user=bucky, elo=1234)
    for index in range(pair_count):
        currency = baker.make('currencies.Currency', owner=dmitry, ticker=f'C{index}')
        AssetPair.objects.create(primary_currency=currency, secondary_currency=tnb_currency)

    request = APIRequestFactory().get('/api/asset-pairs')
    force_authenticate(request, user=bucky)
    with django_assert_num_queries(2):
        response = AssetPairViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 200
    assert response.data['count'] == pair_count
    for pair in response.data['results']:
        assert pair['primary_currency']['owner']['id'] == dmitry.id
        assert pair['primary_currency']['owner']['connect_five_elo'] is None
        assert pair['secondary_currency']['owner']['id'] == bucky.id
        assert pair['secondary_currency']['owner']['connect_five_elo'] == 1234


@pytest.mark.django_db
@pytest.mark.parametrize('order_count', [1, 5])
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_exchange_order_reads_have_constant_queries(
    django_assert_num_queries, bucky, dmitry, tnb_currency, yyy_currency, order_count
):
    buy_orders = [make_buy_order(bucky, tnb_currency, yyy_currency, price=index + 1) for index in range(order_count)]
    sell_orders = [make_sell_order(dmitry, tnb_currency, yyy_currency, price=index + 1) for index in range(order_count)]
    asset_pair_id = buy_orders[0].asset_pair_id

    request = APIRequestFactory().get('/api/exchange-orders')
    force_authenticate(request, user=bucky)
    with django_assert_num_queries(2):
        response = ExchangeOrderViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 200
    assert response.data['count'] == order_count
    assert {order['id'] for order in response.data['results']} == {order.id for order in buy_orders}
    for order in response.data['results']:
        assert order['asset_pair']['primary_currency']['id'] == tnb_currency.id
        assert order['asset_pair']['secondary_currency']['id'] == yyy_currency.id

    request = APIRequestFactory().get('/api/exchange-orders/book', {'asset_pair': asset_pair_id})
    force_authenticate(request, user=bucky)
    with django_assert_num_queries(2):
        response = ExchangeOrderViewSet.as_view({'get': 'book'})(request)

    assert response.status_code == 200
    assert [order['id'] for order in response.data['buy_orders']] == [order.id for order in reversed(buy_orders)]
    assert [order['id'] for order in response.data['sell_orders']] == [order.id for order in sell_orders]
    assert ExchangeOrder.objects.count() == order_count * 2
