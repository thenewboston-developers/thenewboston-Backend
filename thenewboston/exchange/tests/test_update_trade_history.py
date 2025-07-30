from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from django.db.models import Model
from django.forms.models import model_to_dict
from django.utils import timezone
from model_bakery import baker

from thenewboston.exchange.business_logic.trade_history import update_trade_history
from thenewboston.exchange.models import ExchangeOrder, Trade, TradeHistoryItem
from thenewboston.exchange.models.exchange_order import ExchangeOrderSide
from thenewboston.general.tests.any import ANY_INT
from thenewboston.general.tests.misc import model_to_dict_with_id


# We need just create the object in the database, integrity does not matter in this case and tested elsewhere
@patch('thenewboston.exchange.models.ExchangeOrder.save', new=Model.save)
@patch('thenewboston.wallets.models.Wallet.save', new=Model.save)
@patch('thenewboston.exchange.consumers.trade.TradeConsumer.stream_trade', new=Mock())
def make_trade(primary_currency_id, secondary_currency_id, price, filled_quantity, created_at: datetime | None = None):
    created_at = created_at or timezone.now()
    buy_order = baker.make(
        'exchange.ExchangeOrder',
        side=ExchangeOrderSide.BUY.value,  # type: ignore[attr-defined]
        primary_currency_id=primary_currency_id,
        secondary_currency_id=secondary_currency_id
    )
    sell_order = baker.make(
        'exchange.ExchangeOrder',
        side=ExchangeOrderSide.SELL.value,  # type: ignore[attr-defined]
        primary_currency_id=primary_currency_id,
        secondary_currency_id=secondary_currency_id
    )
    baker.make(
        'exchange.Trade',
        price=price,
        filled_quantity=filled_quantity,
        buy_order=buy_order,
        sell_order=sell_order,
        created_date=created_at
    )


@pytest.mark.usefixtures('tnb_mint', 'yyy_mint', 'zzz_mint')
def test_update_trade_history(api_client, tnb_currency, yyy_currency, zzz_currency):
    # No trade history
    assert not ExchangeOrder.objects.exists()
    assert not Trade.objects.exists()
    assert not TradeHistoryItem.objects.exists()

    # One simple trade
    make_trade(tnb_currency.id, yyy_currency.id, 7, 2)
    assert [
        model_to_dict_with_id(item)
        for item in TradeHistoryItem.objects.order_by('primary_currency__ticker', 'secondary_currency__ticker')
    ] == [{
        'id':
            ANY_INT,
        'primary_currency':
            tnb_currency.id,
        'secondary_currency':
            yyy_currency.id,
        'price':
            7,
        'change_1h':
            0.0,
        'change_24h':
            0.0,
        'change_7d':
            0.0,
        'volume_24h':
            2,
        'market_cap':
            700000,
        'sparkline': [
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, 7
        ]
    }]

    # Another currency pair
    make_trade(tnb_currency.id, zzz_currency.id, 11, 4)
    assert [
        model_to_dict_with_id(item)
        for item in TradeHistoryItem.objects.order_by('primary_currency__ticker', 'secondary_currency__ticker')
    ] == [{
        'id':
            ANY_INT,
        'primary_currency':
            tnb_currency.id,
        'secondary_currency':
            yyy_currency.id,
        'price':
            7,
        'change_1h':
            0.0,
        'change_24h':
            0.0,
        'change_7d':
            0.0,
        'volume_24h':
            2,
        'market_cap':
            700000,
        'sparkline': [
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, 7
        ]
    }, {
        'id':
            ANY_INT,
        'primary_currency':
            tnb_currency.id,
        'secondary_currency':
            zzz_currency.id,
        'price':
            11,
        'change_1h':
            0.0,
        'change_24h':
            0.0,
        'change_7d':
            0.0,
        'volume_24h':
            4,
        'market_cap':
            1100000,
        'sparkline': [
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, 11
        ]
    }]

    # Non-empty sparkline
    base_time = timezone.now() - timedelta(seconds=1)
    make_trade(tnb_currency.id, yyy_currency.id, 11, 3, created_at=base_time - timedelta(hours=1))
    make_trade(tnb_currency.id, yyy_currency.id, 15, 1, created_at=base_time - timedelta(hours=24))
    make_trade(tnb_currency.id, yyy_currency.id, 5, 1, created_at=base_time - timedelta(hours=7 * 24))
    for index in range(12, 22):
        make_trade(tnb_currency.id, yyy_currency.id, index, 1, created_at=base_time - timedelta(hours=index * 6))

    expected_trade_history = [
        {
            'id':
                ANY_INT,
            'primary_currency':
                tnb_currency.id,
            'secondary_currency':
                yyy_currency.id,
            'price':
                7,
            'change_1h':
                pytest.approx((7 - 11) / 11 * 100),
            'change_24h':
                pytest.approx((7 - 15) / 15 * 100),
            'change_7d':
                pytest.approx((7 - 5) / 5 * 100),
            'volume_24h':
                5,
            'market_cap':
                700000,
            'sparkline': [
                5, 5, 5, 5, 5, 5, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 12, 12, 12, 12, 12, 12, 12, 15, 15, 15, 15, 7
            ]  # noqa: E122
        },
        {
            'id':
                ANY_INT,
            'primary_currency':
                tnb_currency.id,
            'secondary_currency':
                zzz_currency.id,
            'price':
                11,
            'change_1h':
                0.0,
            'change_24h':
                0.0,
            'change_7d':
                0.0,
            'volume_24h':
                4,
            'market_cap':
                1100000,
            'sparkline': [
                None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                None, None, None, None, None, None, None, None, None, None, 11
            ]
        }
    ]

    assert [
        model_to_dict_with_id(item)
        for item in TradeHistoryItem.objects.order_by('primary_currency__ticker', 'secondary_currency__ticker')
    ] == expected_trade_history

    TradeHistoryItem.objects.all().delete()
    assert not TradeHistoryItem.objects.exists()

    update_trade_history()
    assert [
        model_to_dict_with_id(item)
        for item in TradeHistoryItem.objects.order_by('primary_currency__ticker', 'secondary_currency__ticker')
    ] == expected_trade_history

    with patch('thenewboston.exchange.models.Trade.save', new=Model.save):  # "forget" to update trade history
        make_trade(tnb_currency.id, zzz_currency.id, 9, 3)
        make_trade(zzz_currency.id, yyy_currency.id, 10, 5)

    assert [
        model_to_dict_with_id(item)
        for item in TradeHistoryItem.objects.order_by('primary_currency__ticker', 'secondary_currency__ticker')
    ] == expected_trade_history

    update_trade_history()
    assert [
        model_to_dict_with_id(item)
        for item in TradeHistoryItem.objects.order_by('primary_currency__ticker', 'secondary_currency__ticker')
    ] != expected_trade_history

    expected_trade_history = [
        {
            'primary_currency':
                tnb_currency.id,
            'secondary_currency':
                yyy_currency.id,
            'price':
                7,
            'change_1h':
                pytest.approx((7 - 11) / 11 * 100),
            'change_24h':
                pytest.approx((7 - 15) / 15 * 100),
            'change_7d':
                pytest.approx((7 - 5) / 5 * 100),
            'volume_24h':
                5,
            'market_cap':
                700000,
            'sparkline': [
                5, 5, 5, 5, 5, 5, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 12, 12, 12, 12, 12, 12, 12, 15, 15, 15, 15, 7
            ]  # noqa: E122
        },
        {
            'primary_currency':
                tnb_currency.id,
            'secondary_currency':
                zzz_currency.id,
            'price':
                9,
            'change_1h':
                0.0,
            'change_24h':
                0.0,
            'change_7d':
                0.0,
            'volume_24h':
                7,
            'market_cap':
                900000,
            'sparkline': [
                None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                None, None, None, None, None, None, None, None, None, None, 9
            ]
        },
        {
            'primary_currency':
                zzz_currency.id,
            'secondary_currency':
                yyy_currency.id,
            'price':
                10,
            'change_1h':
                0.0,
            'change_24h':
                0.0,
            'change_7d':
                0.0,
            'volume_24h':
                5,
            'market_cap':
                3000000,
            'sparkline': [
                None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                None, None, None, None, None, None, None, None, None, None, 10
            ]
        }
    ]
    assert [
        model_to_dict(item, exclude=('id', 'created_date', 'modified_date'))
        for item in TradeHistoryItem.objects.order_by('primary_currency__ticker', 'secondary_currency__ticker')
    ] == expected_trade_history

    response = api_client.get('/api/trade-history-items')
    assert (response.status_code, response.json()) == (
        200, {
            'count':
                3,
            'next':
                None,
            'previous':
                None,
            'results': [{
                'primary_currency': {
                    'id': tnb_currency.id,
                    'logo': None,
                    'ticker': 'TNB'
                },
                'secondary_currency': {
                    'id': yyy_currency.id,
                    'logo': None,
                    'ticker': 'YYY'
                },
                'price':
                    7,
                'change_1h':
                    -36.36363636363637,
                'change_24h':
                    -53.333333333333336,
                'change_7d':
                    39.99999999999999,
                'volume_24h':
                    5,
                'market_cap':
                    700000,
                'sparkline': [
                    5, 5, 5, 5, 5, 5, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 12, 12, 12, 12, 12, 12, 12, 15, 15, 15,
                    15, 7
                ]
            }, {
                'primary_currency': {
                    'id': tnb_currency.id,
                    'logo': None,
                    'ticker': 'TNB'
                },
                'secondary_currency': {
                    'id': zzz_currency.id,
                    'logo': None,
                    'ticker': 'ZZZ'
                },
                'price':
                    9,
                'change_1h':
                    0.0,
                'change_24h':
                    0.0,
                'change_7d':
                    0.0,
                'volume_24h':
                    7,
                'market_cap':
                    900000,
                'sparkline': [
                    None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                    None, None, None, None, None, None, None, None, None, None, None, 9
                ]
            }, {
                'primary_currency': {
                    'id': zzz_currency.id,
                    'logo': None,
                    'ticker': 'ZZZ'
                },
                'secondary_currency': {
                    'id': yyy_currency.id,
                    'logo': None,
                    'ticker': 'YYY'
                },
                'price':
                    10,
                'change_1h':
                    0.0,
                'change_24h':
                    0.0,
                'change_7d':
                    0.0,
                'volume_24h':
                    5,
                'market_cap':
                    3000000,
                'sparkline': [
                    None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                    None, None, None, None, None, None, None, None, None, None, None, 10
                ]
            }]
        }
    )
