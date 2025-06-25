import pytest

from thenewboston.exchange.models import ExchangeOrder
from thenewboston.general.tests.misc import model_to_dict_with_id

from ..factories.exchange_order import make_buy_order


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet')
def test_cannot_move_order_to_unpermitted_status(authenticated_api_client, bucky, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    order = make_buy_order(bucky, tnb_currency, yyy_currency, price=100)
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': order.created_date,
        'modified_date': order.modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 1,
        'price': 100,
        'filled_quantity': 0,
        'status': 1,
    }

    response = authenticated_api_client.patch(f'/api/exchange-orders/{order.id}', {'status': 2})  # PARTIAL_FILLED
    assert (response.status_code,
            response.json()) == (400, {
                'status': [{
                    'message': 'Transition is not allowed.',
                    'code': 'invalid'
                }]
            })
    order.refresh_from_db()
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': order.created_date,
        'modified_date': order.modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 1,
        'price': 100,
        'filled_quantity': 0,
        'status': 1,  # no change to status
    }

    response = authenticated_api_client.patch(f'/api/exchange-orders/{order.id}', {'status': 3})
    assert (response.status_code,
            response.json()) == (400, {
                'status': [{
                    'message': 'Transition is not allowed.',
                    'code': 'invalid'
                }]
            })
    order.refresh_from_db()
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': order.created_date,
        'modified_date': order.modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 1,
        'price': 100,
        'filled_quantity': 0,
        'status': 1,  # no change to status
    }

    ExchangeOrder.objects.filter(id=order.id).update(status=3)  # to bypass validation
    order.refresh_from_db()
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': order.created_date,
        'modified_date': order.modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 1,
        'price': 100,
        'filled_quantity': 0,
        'status': 3,
    }

    response = authenticated_api_client.patch(f'/api/exchange-orders/{order.id}', {'status': 100})
    assert (response.status_code, response.json(
    )) == (400, {
        'status': [{
            'message': 'Cannot cancel an order that is in final status.',
            'code': 'invalid'
        }]
    })
    order.refresh_from_db()
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': order.created_date,
        'modified_date': order.modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 1,
        'price': 100,
        'filled_quantity': 0,
        'status': 3,  # no change to status
    }
