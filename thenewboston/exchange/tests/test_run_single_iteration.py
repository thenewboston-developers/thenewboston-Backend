from unittest.mock import patch

import pytest
from django.test import override_settings

from thenewboston.exchange.models import ExchangeOrder, Trade
from thenewboston.exchange.order_processing.engine import get_potentially_matching_orders, run_single_iteration
from thenewboston.general.advisory_locks import clear_all_advisory_locks
from thenewboston.general.tests.any import ANY_DATETIME, ANY_INT, ANY_STR
from thenewboston.general.tests.misc import model_to_dict_with_id
from thenewboston.wallets.models import Wallet

from .base import has_advisory_locks
from .factories.exchange_order import make_buy_order, make_sell_order


@pytest.mark.django_db
@pytest.mark.usefixtures('lock_order_processing')
def test_run_single_iteration__matching_by_price_exactly(
    bucky, bucky_yyy_wallet, dmitry, dmitry_tnb_wallet, tnb_currency, yyy_currency
):
    assert Wallet.objects.count() == 2
    assert not ExchangeOrder.objects.exists()

    assert not Trade.objects.exists()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
        'balance': 1000,
    }
    assert model_to_dict_with_id(dmitry_tnb_wallet) == {
        'id': dmitry_tnb_wallet.id,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'owner': dmitry.id,
        'currency': tnb_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
        'balance': 1000,
    }

    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=102, quantity=5)
    bucky_yyy_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
        'balance': 1000 - 102 * 5,  # balance reserved for the order
    }

    sell_order = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100, quantity=3)
    dmitry_tnb_wallet.refresh_from_db()
    assert model_to_dict_with_id(dmitry_tnb_wallet) == {
        'id': dmitry_tnb_wallet.id,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'owner': dmitry.id,
        'currency': tnb_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
        'balance': 1000 - 3,  # balance reserved for the order
    }

    assert not has_advisory_locks()
    run_single_iteration()
    assert not has_advisory_locks()

    assert Wallet.objects.count() == 4

    trade = Trade.objects.get_or_none()
    assert trade is not None

    assert model_to_dict_with_id(trade) == {
        'id': trade.id,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'buy_order': buy_order.id,
        'sell_order': sell_order.id,
        'filled_quantity': 3,
        'price': 100,
        'overpayment_amount': 6,  # 3 * (102 - 100)
    }

    assert trade.created_date == trade.modified_date
    trade_at = trade.created_date

    buy_order.refresh_from_db()
    assert model_to_dict_with_id(buy_order) == {
        'id': buy_order.id,
        'created_date': ANY_DATETIME,
        'modified_date': trade_at,
        'owner': bucky.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': 1,
        'quantity': 5,
        'price': 102,
        'filled_quantity': 3,
        'status': 2,  # PARTIALLY_FILLED
    }

    sell_order.refresh_from_db()
    assert model_to_dict_with_id(sell_order) == {
        'id': sell_order.id,
        'created_date': ANY_DATETIME,
        'modified_date': trade_at,
        'owner': dmitry.id,
        'primary_currency': tnb_currency.id,
        'secondary_currency': yyy_currency.id,
        'side': -1,
        'quantity': 3,
        'price': 100,
        'filled_quantity': 3,
        'status': 3,  # FILLED
    }

    assert Wallet.objects.count() == 4

    bucky_yyy_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': ANY_DATETIME,
        'modified_date': trade_at,
        'owner': bucky.id,
        'currency': yyy_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
        'balance': 1000 - 102 * 5 + 6,  # overpayment returned
    }

    assert model_to_dict_with_id(dmitry_tnb_wallet) == {
        'id': dmitry_tnb_wallet.id,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'owner': dmitry.id,
        'currency': tnb_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
        'balance': 1000 - 3,  # balance reserved for the order
    }

    # Check created wallets
    bucky_tnb_wallet = Wallet.objects.get(owner=bucky, currency=tnb_currency)
    assert model_to_dict_with_id(bucky_tnb_wallet) == {
        'id': bucky_tnb_wallet.id,
        'created_date': trade_at,
        'modified_date': trade_at,
        'owner': bucky.id,
        'currency': tnb_currency.id,
        'balance': 3,
        'deposit_account_number': ANY_STR,
        'deposit_balance': 0,
        'deposit_signing_key': ANY_STR,
    }

    dmitry_yyy_wallet = Wallet.objects.get(owner=dmitry, currency=yyy_currency)
    assert model_to_dict_with_id(dmitry_yyy_wallet) == {
        'id': dmitry_yyy_wallet.id,
        'created_date': trade_at,
        'modified_date': trade_at,
        'owner': dmitry.id,
        'currency': yyy_currency.id,
        'balance': 300,
        'deposit_account_number': ANY_STR,
        'deposit_balance': 0,
        'deposit_signing_key': ANY_STR,
    }


@pytest.mark.django_db
@pytest.mark.usefixtures('lock_order_processing')
def test_run_single_iteration__buy_order_exhaust_sell_and_another_pair_starts(
    bucky, dmitry, tnb_currency, yyy_currency, zzz_currency, bucky_yyy_wallet, bucky_zzz_wallet, dmitry_tnb_wallet
):
    assert not ExchangeOrder.objects.exists()
    assert zzz_currency.id > yyy_currency.id

    assert ExchangeOrder.objects.count() == 0

    # Open buy/sell orders (matching prices)
    buy_order = make_buy_order(bucky, tnb_currency, yyy_currency, price=102, quantity=9)
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=101, quantity=3)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100, quantity=2)
    sell_order_3 = make_sell_order(
        dmitry, tnb_currency, yyy_currency, price=99, quantity=3, status=2
    )  # PARTIALLY_FILLED

    # Different currency pairs (matching)
    buy_order_other_currency = make_buy_order(bucky, tnb_currency, zzz_currency, price=200)
    sell_order_other_currency = make_sell_order(dmitry, tnb_currency, zzz_currency, price=199)

    assert get_potentially_matching_orders() == [  # assert for the test debugging purposes
        sell_order_3,
        sell_order_2,
        sell_order_1,
        sell_order_other_currency,
        buy_order_other_currency,
        buy_order,
    ]
    clear_all_advisory_locks()  # because of previous call: get_potentially_matching_orders()

    bucky_yyy_wallet.refresh_from_db()
    bucky_zzz_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()

    assert bucky_yyy_wallet.balance == 1000 - 102 * 9
    assert bucky_zzz_wallet.balance == 1000 - 200
    assert dmitry_tnb_wallet.balance == 1000 - 3 - 2 - 3 - 1

    assert not has_advisory_locks()
    run_single_iteration()
    assert not has_advisory_locks()

    trades = list(Trade.objects.order_by('price'))
    assert len(trades) == 4
    assert {trade.created_date for trade in trades} == {trades[0].created_date}
    assert {trade.modified_date for trade in trades} == {trades[0].modified_date}

    expected_trades = [
        (buy_order.id, sell_order_3.id, 3, 99, (102 - 99) * 3),
        (buy_order.id, sell_order_2.id, 2, 100, (102 - 100) * 2),
        (buy_order.id, sell_order_1.id, 3, 101, (102 - 101) * 3),
        (buy_order_other_currency.id, sell_order_other_currency.id, 1, 199, (200 - 199) * 1),
    ]

    for trade, (buy_id, sell_id, qty, price, overpayment_amount) in zip(trades, expected_trades):
        assert model_to_dict_with_id(trade) == {
            'id': trade.id,
            'created_date': ANY_DATETIME,
            'modified_date': ANY_DATETIME,
            'buy_order': buy_id,
            'sell_order': sell_id,
            'filled_quantity': qty,
            'price': price,
            'overpayment_amount': overpayment_amount,
        }

    buy_order.refresh_from_db()
    buy_order_other_currency.refresh_from_db()
    sell_order_1.refresh_from_db()
    sell_order_2.refresh_from_db()
    sell_order_3.refresh_from_db()
    sell_order_other_currency.refresh_from_db()

    # Final statuses:
    assert buy_order.filled_quantity == 8
    assert buy_order.status == 2  # PARTIALLY_FILLED

    assert buy_order_other_currency.filled_quantity == 1
    assert buy_order_other_currency.status == 3  # FILLED

    assert sell_order_1.filled_quantity == 3
    assert sell_order_1.status == 3  # FILLED

    assert sell_order_2.filled_quantity == 2
    assert sell_order_2.status == 3  # FILLED

    assert sell_order_3.filled_quantity == 3
    assert sell_order_3.status == 3  # FILLED

    assert sell_order_other_currency.filled_quantity == 1
    assert sell_order_other_currency.status == 3  # FILLED

    # Check wallet balances
    bucky_tnb_wallet = Wallet.objects.get(owner=bucky, currency=tnb_currency)
    dmitry_yyy_wallet = Wallet.objects.get(owner=dmitry, currency=yyy_currency)
    dmitry_zzz_wallet = Wallet.objects.get(owner=dmitry, currency=zzz_currency)

    assert bucky_tnb_wallet.balance == 9  # 3 + 2 + 3 + 1 (from all trades)

    assert dmitry_yyy_wallet.balance == 3 * 101 + 2 * 100 + 3 * 99  # = 303 + 200 + 297 = 800
    assert dmitry_zzz_wallet.balance == 199

    # Bucky overpayments refunded
    bucky_yyy_wallet = Wallet.objects.get(owner=bucky, currency=yyy_currency)
    assert bucky_yyy_wallet.balance == 1000 - 102 * 9 + (3 * (102 - 101) + 2 * (102 - 100) + 3 * (102 - 99))  # refund

    bucky_zzz_wallet = Wallet.objects.get(owner=bucky, currency=zzz_currency)
    assert bucky_zzz_wallet.balance == 1000 - 200 * 1 + (200 - 199)  # refund


@pytest.mark.django_db
@pytest.mark.usefixtures('lock_order_processing')
@pytest.mark.usefixtures('bucky_yyy_wallet', 'bucky_zzz_wallet', 'dmitry_tnb_wallet', 'dmitry_zzz_wallet')
def test_run_single_iteration__no_trade_situation(bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()

    assert get_potentially_matching_orders() == []
    with patch('thenewboston.exchange.order_processing.engine.make_trade') as make_trade_mock:
        assert not has_advisory_locks()
        run_single_iteration()
        assert not has_advisory_locks()
    make_trade_mock.assert_not_called()
    assert not Trade.objects.exists()

    make_buy_order(bucky, tnb_currency, yyy_currency, price=102)
    assert get_potentially_matching_orders() == []
    with patch('thenewboston.exchange.order_processing.engine.make_trade') as make_trade_mock:
        assert not has_advisory_locks()
        run_single_iteration()
        assert not has_advisory_locks()
    make_trade_mock.assert_not_called()
    assert not Trade.objects.exists()

    make_sell_order(dmitry, tnb_currency, yyy_currency, price=105)
    assert get_potentially_matching_orders() == []
    with patch('thenewboston.exchange.order_processing.engine.make_trade') as make_trade_mock:
        assert not has_advisory_locks()
        run_single_iteration()
        assert not has_advisory_locks()
    make_trade_mock.assert_not_called()
    assert not Trade.objects.exists()


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'dmitry_tnb_wallet')
@pytest.mark.usefixtures('lock_order_processing')
def test_multiple_calls(bucky, dmitry, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    assert not Trade.objects.exists()

    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=10)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=9, quantity=8)
    sell_order_3 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=8, quantity=10)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=10, quantity=12)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=11, quantity=3)

    # Call 1
    with override_settings(ONE_TRADE_PER_ITERATION=True):
        assert run_single_iteration()

    sell_order_1.refresh_from_db()
    sell_order_2.refresh_from_db()
    sell_order_3.refresh_from_db()
    buy_order_1.refresh_from_db()
    buy_order_2.refresh_from_db()

    assert sell_order_3.status == 2  # PARTIALLY_FILLED
    assert sell_order_3.filled_quantity == 3
    assert sell_order_2.status == 1
    assert sell_order_1.status == 1
    assert buy_order_1.status == 1
    assert buy_order_2.status == 3  # FILLED
    assert buy_order_2.filled_quantity == 3
    assert not has_advisory_locks()

    expected_trades = [{
        'id': ANY_INT,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'buy_order': buy_order_2.id,
        'sell_order': sell_order_3.id,
        'filled_quantity': 3,
        'price': 8,
        'overpayment_amount': 9
    }]
    assert [model_to_dict_with_id(trade) for trade in Trade.objects.order_by('created_date')] == expected_trades

    # Call 2
    with override_settings(ONE_TRADE_PER_ITERATION=True):
        assert run_single_iteration()

    sell_order_1.refresh_from_db()
    sell_order_2.refresh_from_db()
    sell_order_3.refresh_from_db()
    buy_order_1.refresh_from_db()
    buy_order_2.refresh_from_db()

    assert sell_order_3.status == 3  # FILLED
    assert sell_order_3.filled_quantity == 10
    assert sell_order_2.status == 1
    assert sell_order_1.status == 1
    assert buy_order_1.status == 2  # PARTIALLY_FILLED
    assert buy_order_1.filled_quantity == 7
    assert buy_order_2.status == 3  # FILLED
    assert buy_order_2.filled_quantity == 3
    assert not has_advisory_locks()

    expected_trades.append({
        'id': ANY_INT,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'buy_order': buy_order_1.id,
        'sell_order': sell_order_3.id,
        'filled_quantity': 7,
        'price': 8,
        'overpayment_amount': 14
    })
    assert [model_to_dict_with_id(trade) for trade in Trade.objects.order_by('created_date')] == expected_trades

    # Call 3
    with override_settings(ONE_TRADE_PER_ITERATION=True):
        assert not run_single_iteration()

    sell_order_1.refresh_from_db()
    sell_order_2.refresh_from_db()
    sell_order_3.refresh_from_db()
    buy_order_1.refresh_from_db()
    buy_order_2.refresh_from_db()

    assert sell_order_3.status == 3  # FILLED
    assert sell_order_3.filled_quantity == 10
    assert sell_order_2.status == 2  # PARTIALLY_FILLED
    assert sell_order_2.filled_quantity == 5
    assert sell_order_1.status == 1
    assert buy_order_1.status == 3  # FILLED
    assert buy_order_1.filled_quantity == 12
    assert buy_order_2.status == 3  # FILLED
    assert buy_order_2.filled_quantity == 3
    assert not has_advisory_locks()

    expected_trades.append({
        'id': ANY_INT,
        'created_date': ANY_DATETIME,
        'modified_date': ANY_DATETIME,
        'buy_order': buy_order_1.id,
        'sell_order': sell_order_2.id,
        'filled_quantity': 5,
        'price': 9,
        'overpayment_amount': 5
    })
    assert [model_to_dict_with_id(trade) for trade in Trade.objects.order_by('created_date')] == expected_trades
