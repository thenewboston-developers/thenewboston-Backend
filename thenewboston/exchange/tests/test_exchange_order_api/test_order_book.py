import pytest

from thenewboston.exchange.models import AssetPair, ExchangeOrder
from thenewboston.general.utils.datetime import to_iso_format

from ..factories.exchange_order import make_buy_order, make_sell_order


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
def test_get_order_book__smoke_test(authenticated_api_client, dmitry, bucky, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=10)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=9, quantity=8)
    sell_order_3 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=8, quantity=10)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=10, quantity=12)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=11, quantity=3)

    asset_pair, _ = AssetPair.objects.get_or_create(primary_currency=tnb_currency, secondary_currency=yyy_currency)
    response = authenticated_api_client.get(
        f'/api/exchange-orders/book?primary_currency={tnb_currency.id}&secondary_currency={yyy_currency.id}'
    )
    assert (response.status_code, response.json()) == (
        200, {
            'sell_orders': [{
                'id': sell_order_3.id,
                'created_date': to_iso_format(sell_order_3.created_date),
                'modified_date': to_iso_format(sell_order_3.modified_date),
                'side': -1,
                'quantity': 10,
                'price': 8,
                'filled_quantity': 0,
                'status': 1,
                'owner': dmitry.id,
                'asset_pair': {
                    'id': asset_pair.id,
                    'primary_currency': {
                        'id': tnb_currency.id,
                        'ticker': tnb_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                    },
                    'secondary_currency': {
                        'id': yyy_currency.id,
                        'ticker': yyy_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/yyy_currency.png',
                    }
                }
            }, {
                'id': sell_order_2.id,
                'created_date': to_iso_format(sell_order_2.created_date),
                'modified_date': to_iso_format(sell_order_2.modified_date),
                'side': -1,
                'quantity': 8,
                'price': 9,
                'filled_quantity': 0,
                'status': 1,
                'owner': dmitry.id,
                'asset_pair': {
                    'id': asset_pair.id,
                    'primary_currency': {
                        'id': tnb_currency.id,
                        'ticker': tnb_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                    },
                    'secondary_currency': {
                        'id': yyy_currency.id,
                        'ticker': yyy_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/yyy_currency.png',
                    }
                }
            }, {
                'id': sell_order_1.id,
                'created_date': to_iso_format(sell_order_1.created_date),
                'modified_date': to_iso_format(sell_order_1.modified_date),
                'side': -1,
                'quantity': 1,
                'price': 10,
                'filled_quantity': 0,
                'status': 1,
                'owner': dmitry.id,
                'asset_pair': {
                    'id': asset_pair.id,
                    'primary_currency': {
                        'id': tnb_currency.id,
                        'ticker': tnb_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                    },
                    'secondary_currency': {
                        'id': yyy_currency.id,
                        'ticker': yyy_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/yyy_currency.png',
                    }
                }
            }],
            'buy_orders': [{
                'id': buy_order_2.id,
                'created_date': to_iso_format(buy_order_2.created_date),
                'modified_date': to_iso_format(buy_order_2.modified_date),
                'side': 1,
                'quantity': 3,
                'price': 11,
                'filled_quantity': 0,
                'status': 1,
                'owner': bucky.id,
                'asset_pair': {
                    'id': asset_pair.id,
                    'primary_currency': {
                        'id': tnb_currency.id,
                        'ticker': tnb_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                    },
                    'secondary_currency': {
                        'id': yyy_currency.id,
                        'ticker': yyy_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/yyy_currency.png',
                    }
                }
            }, {
                'id': buy_order_1.id,
                'created_date': to_iso_format(buy_order_1.created_date),
                'modified_date': to_iso_format(buy_order_1.modified_date),
                'side': 1,
                'quantity': 12,
                'price': 10,
                'filled_quantity': 0,
                'status': 1,
                'owner': bucky.id,
                'asset_pair': {
                    'id': asset_pair.id,
                    'primary_currency': {
                        'id': tnb_currency.id,
                        'ticker': tnb_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                    },
                    'secondary_currency': {
                        'id': yyy_currency.id,
                        'ticker': yyy_currency.ticker,
                        'logo': 'http://localhost:8000/media/images/yyy_currency.png',
                    }
                }
            }]
        }
    )
