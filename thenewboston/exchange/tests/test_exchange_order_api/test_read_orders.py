import pytest

from thenewboston.exchange.models import ExchangeOrder
from thenewboston.general.utils.datetime import to_iso_format


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'bucky_tnb_wallet', 'dmitry_yyy_wallet')
def test_list_exchange_orders(authenticated_api_client, api_client, bucky, dmitry, tnb_currency, yyy_currency):
    bucky_order1 = ExchangeOrder.objects.create(
        owner=bucky,
        primary_currency=tnb_currency,
        secondary_currency=yyy_currency,
        side=1,
        quantity=5,
        price=50,
    )
    bucky_order2 = ExchangeOrder.objects.create(
        owner=bucky,
        primary_currency=tnb_currency,
        secondary_currency=yyy_currency,
        side=-1,
        quantity=3,
        price=75,
    )
    dmitry_order = ExchangeOrder.objects.create(
        owner=dmitry,
        primary_currency=tnb_currency,
        secondary_currency=yyy_currency,
        side=1,
        quantity=3,
        price=100,
    )

    response = authenticated_api_client.get('/api/exchange-orders')
    assert (response.status_code, response.json()) == (
        200, {
            'count':
                2,
            'next':
                None,
            'previous':
                None,
            'results': [{
                'id': bucky_order2.id,
                'created_date': to_iso_format(bucky_order2.created_date),
                'modified_date': to_iso_format(bucky_order2.modified_date),
                'side': -1,
                'quantity': 3,
                'price': 75,
                'filled_quantity': 0,
                'status': 1,
                'owner': bucky.id,
                'primary_currency': tnb_currency.id,
                'secondary_currency': yyy_currency.id,
            }, {
                'id': bucky_order1.id,
                'created_date': to_iso_format(bucky_order1.created_date),
                'modified_date': to_iso_format(bucky_order1.modified_date),
                'side': 1,
                'quantity': 5,
                'price': 50,
                'filled_quantity': 0,
                'status': 1,
                'owner': bucky.id,
                'primary_currency': tnb_currency.id,
                'secondary_currency': yyy_currency.id,
            }]
        }
    )

    response = authenticated_api_client.get(f'/api/exchange-orders/{bucky_order1.id}')
    assert (response.status_code, response.json()) == (
        200, {
            'id': bucky_order1.id,
            'created_date': to_iso_format(bucky_order1.created_date),
            'modified_date': to_iso_format(bucky_order1.modified_date),
            'side': 1,
            'quantity': 5,
            'price': 50,
            'filled_quantity': 0,
            'status': 1,
            'owner': bucky.id,
            'primary_currency': tnb_currency.id,
            'secondary_currency': yyy_currency.id,
        }
    )

    response = authenticated_api_client.get(f'/api/exchange-orders/{dmitry_order.id}')
    assert (response.status_code, response.json()) == (404, {'detail': 'No ExchangeOrder matches the given query.'})

    response = api_client.get('/api/exchange-orders')
    assert (response.status_code, response.json()
            ) == (401, {
                'message': 'Authentication credentials were not provided.',
                'code': 'not_authenticated'
            })

    response = api_client.get(f'/api/exchange-orders/{bucky_order1.id}')
    assert (response.status_code, response.json()
            ) == (401, {
                'message': 'Authentication credentials were not provided.',
                'code': 'not_authenticated'
            })
