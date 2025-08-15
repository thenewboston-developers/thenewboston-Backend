from datetime import datetime, timezone
from unittest.mock import call, patch

from pytest_parametrize_cases import Case, parametrize_cases

from thenewboston.exchange.order_processing.engine import make_trade
from thenewboston.general.enums import MessageType
from thenewboston.general.tests.any import ANY_DATETIME_STR, ANY_INT, ANY_STR
from thenewboston.general.tests.misc import model_to_dict_with_id
from thenewboston.general.utils.datetime import to_iso_format
from thenewboston.wallets.models import Wallet

from .factories.exchange_order import make_buy_order, make_sell_order
from ..models import AssetPair, Trade


@parametrize_cases(
    Case(
        'Completely fill both orders',
        buy_quantity=2,
        sell_quantity=2,
        buy_price=105,
        sell_price=101,
    ),
    Case(
        'Completely fill buy order, partially fill sell order',
        buy_quantity=3,
        sell_quantity=7,
        buy_price=105,
        sell_price=101,
    ),
    Case(
        'Completely fill sell order, partially fill buy order',
        buy_quantity=5,
        sell_quantity=1,
        buy_price=105,
        sell_price=101,
    ),
    Case(
        'Price parity and completely fill both orders',
        buy_quantity=2,
        sell_quantity=2,
        buy_price=101,
        sell_price=101,
    ),
    Case(
        'Price parity and completely fill buy order, partially fill sell order',
        buy_quantity=3,
        sell_quantity=7,
        buy_price=101,
        sell_price=101,
    ),
    Case(
        'Price parity and completely fill sell order, partially fill buy order',
        buy_quantity=5,
        sell_quantity=1,
        buy_price=101,
        sell_price=101,
    ),
)
def test_make_trade_successfully_creates_trade(
    bucky,
    bucky_yyy_wallet,
    yyy_currency,
    dmitry,
    dmitry_tnb_wallet,
    tnb_currency,
    buy_quantity,
    buy_price,
    sell_quantity,
    sell_price,
):
    # TODO(dmu) LOW: We may want to move some calculated values to parameters similar to how it is done in
    #                `test_make_trade_with_partly_filled_orders`
    assert Wallet.objects.count() == 2
    assert bucky_yyy_wallet.balance == 1000
    assert dmitry_tnb_wallet.balance == 1000

    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet'),
        patch('thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order'),
    ):
        buy_order = make_buy_order(
            owner=bucky,
            primary_currency=tnb_currency,
            secondary_currency=yyy_currency,  # reserves from this currency wallet
            quantity=buy_quantity,
            price=buy_price,
        )
        sell_order = make_sell_order(
            owner=dmitry,
            primary_currency=tnb_currency,  # reserves from this currency wallet
            secondary_currency=yyy_currency,
            quantity=sell_quantity,
            price=sell_price,
        )

    assert Wallet.objects.count() == 2
    bucky_yyy_wallet.refresh_from_db()
    assert bucky_yyy_wallet.balance == 1000 - buy_quantity * buy_price  # spent full buy price
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000 - sell_quantity

    trade_at = datetime.now(timezone.utc)

    assert not Trade.objects.exists()

    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet') as stream_wallet_mock,
        patch(
            'thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order'
        ) as stream_exchange_order_mock,
        patch(
            'thenewboston.notifications.consumers.notification.NotificationConsumer.stream_notification'
        ) as stream_notification_mock,
        patch('thenewboston.exchange.consumers.trade.TradeConsumer.stream_trade') as stream_trade_mock,
    ):
        make_trade(sell_order, buy_order, trade_at)

    trade = Trade.objects.get()
    expected_filled_quantity = min(buy_quantity, sell_quantity)
    price_diff = buy_price - sell_price
    assert trade.buy_order == buy_order
    assert trade.sell_order == sell_order
    assert trade.filled_quantity == expected_filled_quantity
    assert trade.price == sell_price
    assert trade.overpayment_amount == price_diff * expected_filled_quantity
    assert trade.created_date == trade_at
    assert trade.modified_date == trade_at

    buy_order.refresh_from_db()
    expected_buy_order_status = 2 if expected_filled_quantity < buy_quantity else 3  # PARTIALLY_FILLED or FILLED
    assert buy_order.status == expected_buy_order_status
    assert buy_order.filled_quantity == expected_filled_quantity
    assert buy_order.unfilled_quantity == buy_quantity - expected_filled_quantity
    assert buy_order.modified_date == trade_at
    sell_order.refresh_from_db()
    expected_sell_order_status = 2 if expected_filled_quantity < sell_quantity else 3  # PARTIALLY_FILLED or FILLED
    assert sell_order.status == expected_sell_order_status
    assert sell_order.filled_quantity == expected_filled_quantity
    assert sell_order.unfilled_quantity == sell_quantity - expected_filled_quantity
    assert sell_order.modified_date == trade_at

    assert Wallet.objects.count() == 4  # two new wallets created by the trade

    bucky_yyy_wallet.refresh_from_db()
    expected_bucky_yyy_wallet_balance = (  # reserved amount
        1000 - expected_filled_quantity * sell_price - (buy_quantity - expected_filled_quantity) * buy_price
    )
    assert bucky_yyy_wallet.balance == expected_bucky_yyy_wallet_balance
    buy_order_credit_wallet = Wallet.objects.get(owner=bucky, currency=tnb_currency)
    assert model_to_dict_with_id(buy_order_credit_wallet) == {
        'balance': expected_filled_quantity,
        'created_date': trade_at,
        'currency': tnb_currency.id,
        'deposit_account_number': ANY_STR,
        'deposit_balance': 0,
        'deposit_signing_key': ANY_STR,
        'id': buy_order_credit_wallet.id,
        'modified_date': trade_at,
        'owner': bucky.id,
    }

    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000 - sell_quantity  # reserved amount
    sell_order_credit_wallet = Wallet.objects.get(owner=dmitry, currency=yyy_currency)
    assert sell_order_credit_wallet.balance == expected_filled_quantity * sell_price  # received by trade price
    assert sell_order_credit_wallet.created_date == trade_at
    assert sell_order_credit_wallet.modified_date == trade_at

    asset_pair = AssetPair.objects.get(primary_currency=tnb_currency, secondary_currency=yyy_currency)
    stream_trade_mock.assert_called_once_with(
        message_type=MessageType.CREATE_TRADE,
        trade_data={
            'id': trade.id,
            'asset_pair': asset_pair.id,
            'created_date': to_iso_format(trade_at),
            'modified_date': to_iso_format(trade_at),
            'filled_quantity': expected_filled_quantity,
            'price': sell_price,
            'overpayment_amount': price_diff * expected_filled_quantity,
            'buy_order': buy_order.id,
            'sell_order': sell_order.id,
        },
        ticker='TNB',
    )

    stream_exchange_order_mock.assert_has_calls(
        [
            call(
                message_type=MessageType.UPDATE_EXCHANGE_ORDER,
                order_data={
                    'id': buy_order.id,
                    'created_date': to_iso_format(buy_order.created_date),
                    'modified_date': to_iso_format(buy_order.modified_date),
                    'side': 1,
                    'quantity': buy_quantity,
                    'price': buy_price,
                    'filled_quantity': expected_filled_quantity,
                    'status': expected_buy_order_status,
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
                        },
                    },
                },
                primary_currency_id=asset_pair.primary_currency_id,
                secondary_currency_id=asset_pair.secondary_currency_id,
            ),
            call(
                message_type=MessageType.UPDATE_EXCHANGE_ORDER,
                order_data={
                    'id': sell_order.id,
                    'created_date': to_iso_format(sell_order.created_date),
                    'modified_date': to_iso_format(sell_order.modified_date),
                    'side': -1,
                    'quantity': sell_quantity,
                    'price': sell_price,
                    'filled_quantity': expected_filled_quantity,
                    'status': expected_sell_order_status,
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
                        },
                    },
                },
                primary_currency_id=asset_pair.primary_currency_id,
                secondary_currency_id=asset_pair.secondary_currency_id,
            ),
        ]
    )

    expected_stream_notification_mock_calls = []
    if expected_buy_order_status == 3:
        expected_stream_notification_mock_calls.append(
            call(
                message_type=MessageType.CREATE_NOTIFICATION,
                notification_data={
                    'id': ANY_INT,
                    'created_date': ANY_DATETIME_STR,
                    'modified_date': ANY_DATETIME_STR,
                    'payload': {
                        'notification_type': 'EXCHANGE_ORDER_FILLED',
                        'order_id': buy_order.id,
                        'side': 1,
                        'quantity': expected_filled_quantity,
                        'price': buy_price,
                        'primary_currency': {
                            'id': tnb_currency.id,
                            'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                            'ticker': 'TNB',
                        },
                        'secondary_currency': {
                            'id': yyy_currency.id,
                            'logo': 'http://localhost:8000/media/images/yyy_currency.png',
                            'ticker': 'YYY',
                        },
                    },
                    'is_read': False,
                    'owner': bucky.id,
                },
            )
        )

    if expected_sell_order_status == 3:
        expected_stream_notification_mock_calls.append(
            call(
                message_type=MessageType.CREATE_NOTIFICATION,
                notification_data={
                    'id': ANY_INT,
                    'created_date': ANY_DATETIME_STR,
                    'modified_date': ANY_DATETIME_STR,
                    'payload': {
                        'notification_type': 'EXCHANGE_ORDER_FILLED',
                        'order_id': sell_order.id,
                        'side': -1,
                        'quantity': expected_filled_quantity,
                        'price': sell_price,
                        'primary_currency': {
                            'id': tnb_currency.id,
                            'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                            'ticker': 'TNB',
                        },
                        'secondary_currency': {
                            'id': yyy_currency.id,
                            'logo': 'http://localhost:8000/media/images/yyy_currency.png',
                            'ticker': 'YYY',
                        },
                    },
                    'is_read': False,
                    'owner': dmitry.id,
                },
            )
        )

    stream_notification_mock.assert_has_calls(expected_stream_notification_mock_calls)

    if buy_price == sell_price:
        stream_wallet_mock.assert_not_called()
    else:
        stream_wallet_mock.assert_has_calls(
            [
                call(
                    message_type=MessageType.UPDATE_WALLET,
                    wallet_data={
                        'balance': expected_bucky_yyy_wallet_balance,  # balance after overpayment is returned
                        'currency': {
                            'id': yyy_currency.id,
                            'owner': {
                                'avatar': None,
                                'banner': None,
                                'bio': '',
                                'discord_username': None,
                                'facebook_username': None,
                                'github_username': None,
                                'id': bucky.id,
                                'instagram_username': None,
                                'is_staff': False,
                                'linkedin_username': None,
                                'pinterest_username': None,
                                'reddit_username': None,
                                'tiktok_username': None,
                                'twitch_username': None,
                                'username': 'bucky',
                                'x_username': None,
                                'youtube_username': None,
                            },
                            'discord_username': None,
                            'facebook_username': None,
                            'github_username': None,
                            'instagram_username': None,
                            'linkedin_username': None,
                            'pinterest_username': None,
                            'reddit_username': None,
                            'tiktok_username': None,
                            'twitch_username': None,
                            'x_username': None,
                            'youtube_username': None,
                            'created_date': to_iso_format(yyy_currency.created_date),
                            'modified_date': to_iso_format(yyy_currency.modified_date),
                            'description': None,
                            'domain': 'yyy.net',
                            'logo': 'http://localhost:8000/media/images/yyy_currency.png',
                            'ticker': 'YYY',
                        },
                        'created_date': to_iso_format(bucky_yyy_wallet.created_date),
                        'deposit_account_number': None,
                        'deposit_balance': 0,
                        'id': bucky_yyy_wallet.id,
                        'modified_date': to_iso_format(bucky_yyy_wallet.modified_date),
                        'owner': bucky_yyy_wallet.owner_id,
                    },
                ),
            ]
        )


@parametrize_cases(
    Case(
        'Both unfilled orders',
        buy_filled_quantity=0,
        sell_filled_quantity=0,
        expected_buy_order_status=3,
        expected_sell_order_status=2,
        expected_filled_quantity=3,
    ),
    Case(
        'Buy order partly filled',
        buy_filled_quantity=1,
        sell_filled_quantity=0,
        expected_buy_order_status=3,
        expected_sell_order_status=2,
        expected_filled_quantity=2,
    ),
    Case(
        'Sell order partly filled',
        buy_filled_quantity=0,
        sell_filled_quantity=1,
        expected_buy_order_status=3,
        expected_sell_order_status=2,
        expected_filled_quantity=3,
    ),
    Case(
        'Both orders partly filled',
        buy_filled_quantity=1,
        sell_filled_quantity=1,
        expected_buy_order_status=3,
        expected_sell_order_status=2,
        expected_filled_quantity=2,
    ),
    Case(
        'Sell order filled, so both order get filled',
        buy_filled_quantity=0,
        sell_filled_quantity=4,
        expected_buy_order_status=3,
        expected_sell_order_status=3,
        expected_filled_quantity=3,
    ),
    Case(
        'Sell order filled, so buy order stays partly filled',
        buy_filled_quantity=0,
        sell_filled_quantity=5,
        expected_buy_order_status=2,
        expected_sell_order_status=3,
        expected_filled_quantity=2,
    ),
)
def test_make_trade_with_partly_filled_orders(
    bucky,
    bucky_yyy_wallet,
    yyy_currency,
    dmitry,
    dmitry_tnb_wallet,
    tnb_currency,
    buy_filled_quantity,
    sell_filled_quantity,
    expected_buy_order_status,
    expected_sell_order_status,
    expected_filled_quantity,
):
    buy_quantity = 3
    sell_quantity = 7
    buy_price = 105
    sell_price = 101

    assert Wallet.objects.count() == 2
    assert bucky_yyy_wallet.balance == 1000
    assert dmitry_tnb_wallet.balance == 1000

    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet'),
        patch('thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order'),
    ):
        buy_order = make_buy_order(
            owner=bucky,
            primary_currency=tnb_currency,
            secondary_currency=yyy_currency,  # reserves from this currency wallet
            quantity=buy_quantity,
            price=buy_price,
        )
        buy_order.filled_quantity = buy_filled_quantity
        buy_order.save()
        assert buy_order.status == (2 if buy_filled_quantity else 1)

        sell_order = make_sell_order(
            owner=dmitry,
            primary_currency=tnb_currency,  # reserves from this currency wallet
            secondary_currency=yyy_currency,
            quantity=sell_quantity,
            price=sell_price,
        )
        sell_order.filled_quantity = sell_filled_quantity
        sell_order.save()
        assert sell_order.status == (2 if sell_filled_quantity else 1)

    assert Wallet.objects.count() == 2
    bucky_yyy_wallet.refresh_from_db()
    assert bucky_yyy_wallet.balance == 1000 - buy_quantity * buy_price  # spent full buy price
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000 - sell_quantity

    trade_at = datetime.now(timezone.utc)

    assert not Trade.objects.exists()

    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet'),
        patch('thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order'),
        patch('thenewboston.notifications.consumers.notification.NotificationConsumer.stream_notification'),
        patch('thenewboston.exchange.consumers.trade.TradeConsumer.stream_trade'),
    ):
        make_trade(sell_order, buy_order, trade_at)

    trade = Trade.objects.get()

    # The following assert is to help produce parameterization in case of changes in future
    assert expected_filled_quantity == min(buy_quantity - buy_filled_quantity, sell_quantity - sell_filled_quantity)

    price_diff = buy_price - sell_price
    assert trade.buy_order == buy_order
    assert trade.sell_order == sell_order
    assert trade.filled_quantity == expected_filled_quantity
    assert trade.price == sell_price
    assert trade.overpayment_amount == price_diff * expected_filled_quantity
    assert trade.created_date == trade_at
    assert trade.modified_date == trade_at

    buy_order.refresh_from_db()
    # The following assert is to help produce parameterization in case of changes in future
    assert (
        expected_buy_order_status == 2 if expected_filled_quantity < (buy_quantity - buy_filled_quantity) else 3
    )  # PARTIALLY_FILLED or FILLED
    assert buy_order.status == expected_buy_order_status
    assert buy_order.filled_quantity == expected_filled_quantity + buy_filled_quantity
    assert buy_order.unfilled_quantity == buy_quantity - expected_filled_quantity - buy_filled_quantity
    assert buy_order.modified_date == trade_at
    sell_order.refresh_from_db()

    # The following assert is to help produce parameterization in case of changes in future
    assert (
        expected_sell_order_status == 2 if expected_filled_quantity < (sell_quantity - sell_filled_quantity) else 3
    )  # PARTIALLY_FILLED or FILLED
    assert sell_order.status == expected_sell_order_status
    assert sell_order.filled_quantity == expected_filled_quantity + sell_filled_quantity
    assert sell_order.unfilled_quantity == sell_quantity - expected_filled_quantity - sell_filled_quantity
    assert sell_order.modified_date == trade_at

    assert Wallet.objects.count() == 4  # two new wallets created by the trade

    bucky_yyy_wallet.refresh_from_db()
    expected_bucky_yyy_wallet_balance = (  # reserved amount
        1000
        - expected_filled_quantity * sell_price
        - (
            buy_quantity - expected_filled_quantity  # We do not subtract `buy_filled_quantity` on purpose here
        )
        * buy_price
    )
    assert bucky_yyy_wallet.balance == expected_bucky_yyy_wallet_balance
    buy_order_credit_wallet = Wallet.objects.get(owner=bucky, currency=tnb_currency)
    assert buy_order_credit_wallet.balance == expected_filled_quantity
    assert buy_order_credit_wallet.created_date == trade_at
    assert buy_order_credit_wallet.modified_date == trade_at

    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000 - sell_quantity  # reserved amount
    sell_order_credit_wallet = Wallet.objects.get(owner=dmitry, currency=yyy_currency)
    assert sell_order_credit_wallet.balance == expected_filled_quantity * sell_price  # received by trade price
    assert sell_order_credit_wallet.created_date == trade_at
    assert sell_order_credit_wallet.modified_date == trade_at
