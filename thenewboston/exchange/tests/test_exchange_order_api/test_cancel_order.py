import pytest

from thenewboston.exchange.models import ExchangeOrder
from thenewboston.general.tests.misc import model_to_dict_with_id

from ..factories.exchange_order import make_buy_order, make_sell_order


@pytest.mark.django_db
def test_cancel_buy_order(authenticated_api_client, bucky, tnb_currency, yyy_currency, bucky_yyy_wallet):
    assert not ExchangeOrder.objects.exists()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': bucky_yyy_wallet.modified_date,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'balance': 1000,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None
    }

    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=101, quantity=2)
    before_update_created_date = buy_order.created_date
    before_update_modified_date = buy_order.modified_date

    bucky_yyy_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': bucky_yyy_wallet.modified_date,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'balance': 1000 - 2 * 101,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None
    }

    response = authenticated_api_client.patch(f'/api/exchange-orders/{buy_order.id}', {'status': 100})
    assert (response.status_code, response.json()) == (
        200, {
            'primary_currency': buy_order.primary_currency_id,
            'secondary_currency': buy_order.secondary_currency_id,
            'side': 1,
            'quantity': 2,
            'price': 101,
            'status': 100
        }
    )
    buy_order.refresh_from_db()
    assert model_to_dict_with_id(buy_order) == {
        'id': buy_order.id,
        'created_date': before_update_created_date,
        'modified_date': buy_order.modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 2,
        'price': 101,
        'filled_quantity': 0,
        'status': 100,
    }
    assert before_update_modified_date < buy_order.modified_date

    bucky_yyy_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': bucky_yyy_wallet.modified_date,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'balance': 1000,  # the balance is restored
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None
    }

    # Idempotency test: cancel the same order again
    buy_order.refresh_from_db()
    before_update_created_date = buy_order.created_date
    before_update_modified_date = buy_order.modified_date
    response = authenticated_api_client.patch(f'/api/exchange-orders/{buy_order.id}', {'status': 100})
    assert (response.status_code, response.json()) == (
        200, {
            'primary_currency': buy_order.primary_currency_id,
            'secondary_currency': buy_order.secondary_currency_id,
            'side': 1,
            'quantity': 2,
            'price': 101,
            'status': 100
        }
    )
    buy_order.refresh_from_db()
    assert model_to_dict_with_id(buy_order) == {
        'id': buy_order.id,
        'created_date': before_update_created_date,
        'modified_date': before_update_modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 2,
        'price': 101,
        'filled_quantity': 0,
        'status': 100,
    }

    bucky_yyy_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': bucky_yyy_wallet.modified_date,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'balance': 1000,  # the balance is restored
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None
    }


@pytest.mark.django_db
def test_cancel_sell_order(authenticated_api_client, bucky, tnb_currency, yyy_currency, bucky_tnb_wallet):
    assert not ExchangeOrder.objects.exists()
    assert bucky_tnb_wallet.balance == 1000
    order = make_sell_order(bucky, tnb_currency, yyy_currency, price=101, quantity=2)
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 - 2
    response = authenticated_api_client.patch(f'/api/exchange-orders/{order.id}', {'status': 100})
    assert (response.status_code, response.json()) == (
        200, {
            'primary_currency': order.primary_currency_id,
            'secondary_currency': order.secondary_currency_id,
            'side': -1,
            'quantity': 2,
            'price': 101,
            'status': 100
        }
    )
    order.refresh_from_db()
    assert order.status == 100  # CANCELLED
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000  # the balance is restored


@pytest.mark.django_db
def test_cancel_partly_filled_buy_order(authenticated_api_client, bucky, tnb_currency, yyy_currency, bucky_yyy_wallet):
    assert not ExchangeOrder.objects.exists()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': bucky_yyy_wallet.modified_date,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'balance': 1000,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None
    }

    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=101, quantity=5)
    bucky_yyy_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': bucky_yyy_wallet.modified_date,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'balance': 1000 - 5 * 101,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None
    }

    buy_order.fill_order(2)  # Partially fill the order with 2 units
    buy_order.save()
    buy_order.refresh_from_db()
    assert model_to_dict_with_id(buy_order) == {
        'id': buy_order.id,
        'created_date': buy_order.created_date,
        'modified_date': buy_order.modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 5,
        'price': 101,
        'filled_quantity': 2,
        'status': 2,  # PARTIAL_FILLED
    }

    response = authenticated_api_client.patch(f'/api/exchange-orders/{buy_order.id}', {'status': 100})
    assert (response.status_code, response.json()) == (
        200, {
            'primary_currency': buy_order.primary_currency_id,
            'secondary_currency': buy_order.secondary_currency_id,
            'side': 1,
            'quantity': 5,
            'price': 101,
            'status': 100
        }
    )
    buy_order.refresh_from_db()
    assert model_to_dict_with_id(buy_order) == {
        'id': buy_order.id,
        'created_date': buy_order.created_date,
        'modified_date': buy_order.modified_date,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 5,
        'price': 101,
        'filled_quantity': 2,
        'status': 100,  # CANCELLED
    }

    bucky_yyy_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': bucky_yyy_wallet.modified_date,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'balance': 1000 - 5 * 101 + 3 * 101,  # the balance is restored
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None
    }


@pytest.mark.django_db
@pytest.mark.usefixtures('dmitry_yyy_wallet')
def test_cancel_someones_else_order(authenticated_api_client, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    order = make_buy_order(dmitry, tnb_currency, yyy_currency, price=100)
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': order.created_date,
        'modified_date': order.modified_date,
        'owner': dmitry.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 1,
        'price': 100,
        'filled_quantity': 0,
        'status': 1,
    }

    response = authenticated_api_client.patch(f'/api/exchange-orders/{order.id}', {'status': 100})
    assert (response.status_code, response.json()) == (404, {'detail': 'No ExchangeOrder matches the given query.'})
    order.refresh_from_db()
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': order.created_date,
        'modified_date': order.modified_date,
        'owner': dmitry.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 1,
        'price': 100,
        'filled_quantity': 0,
        'status': 1,
    }
