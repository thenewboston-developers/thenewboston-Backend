from unittest.mock import patch

from thenewboston.general.enums import MessageType
from thenewboston.general.utils.datetime import to_iso_format
from thenewboston.wallets.models import Wallet

from .factories.exchange_order import make_buy_order, make_sell_order


def test_exchange_order_creation(bucky, dmitry, dmitry_tnb_wallet, tnb_currency, bucky_yyy_wallet, yyy_currency):
    assert Wallet.objects.count() == 2
    assert bucky_yyy_wallet.balance == 1000
    assert dmitry_tnb_wallet.balance == 1000

    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet') as stream_wallet_mock,
        patch('thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order') as
        stream_exchange_order_mock,
    ):
        buy_order = make_buy_order(
            owner=bucky,
            primary_currency=tnb_currency,
            secondary_currency=yyy_currency,  # reserves from this currency wallet
            quantity=2,
            price=105
        )

    assert Wallet.objects.count() == 2  # no new wallet created
    bucky_yyy_wallet.refresh_from_db()
    assert bucky_yyy_wallet.balance == 1000 - 2 * 105
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000  # balance remains unchanged

    stream_wallet_mock.assert_called_once_with(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data={
            'balance': 1000 - 2 * 105,
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
                    'youtube_username': None
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
                'logo': None,
                'ticker': 'YYY'
            },
            'created_date': to_iso_format(bucky_yyy_wallet.created_date),
            'deposit_account_number': None,
            'deposit_balance': 0,
            'id': bucky_yyy_wallet.id,
            'modified_date': to_iso_format(bucky_yyy_wallet.modified_date),
            'owner': bucky_yyy_wallet.owner_id,
        }
    )

    stream_exchange_order_mock.assert_called_once_with(
        message_type=MessageType.UPDATE_EXCHANGE_ORDER,
        order_data={
            'id': buy_order.id,
            'created_date': to_iso_format(buy_order.created_date),
            'modified_date': to_iso_format(buy_order.modified_date),
            'side': 1,
            'quantity': 2,
            'price': 105,
            'filled_quantity': 0,
            'status': 1,
            'owner': bucky.id,
            'primary_currency': buy_order.primary_currency_id,
            'secondary_currency': buy_order.secondary_currency_id,
        },
        primary_currency_id=buy_order.primary_currency_id,
        secondary_currency_id=buy_order.secondary_currency_id,
    )

    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet') as stream_wallet_mock,
        patch('thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order') as
        stream_exchange_order_mock,
    ):
        sell_order = make_sell_order(
            owner=dmitry,
            primary_currency=tnb_currency,  # reserves from this currency wallet
            secondary_currency=yyy_currency,
            quantity=3,
            price=101
        )

    assert Wallet.objects.count() == 2  # no new wallet created
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000 - 3
    bucky_yyy_wallet.refresh_from_db()
    assert bucky_yyy_wallet.balance == 1000 - 2 * 105  # balance remains unchanged

    stream_wallet_mock.assert_called_once_with(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data={
            'balance': 1000 - 3,
            'currency': {
                'id': tnb_currency.id,
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
                    'youtube_username': None
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
                'created_date': to_iso_format(tnb_currency.created_date),
                'modified_date': to_iso_format(tnb_currency.modified_date),
                'description': None,
                'domain': 'thenewboston.net',
                'logo': None,
                'ticker': 'TNB'
            },
            'created_date': to_iso_format(dmitry_tnb_wallet.created_date),
            'deposit_account_number': None,
            'deposit_balance': 0,
            'id': dmitry_tnb_wallet.id,
            'modified_date': to_iso_format(dmitry_tnb_wallet.modified_date),
            'owner': dmitry_tnb_wallet.owner_id,
        }
    )

    stream_exchange_order_mock.assert_called_once_with(
        message_type=MessageType.UPDATE_EXCHANGE_ORDER,
        order_data={
            'id': sell_order.id,
            'created_date': to_iso_format(sell_order.created_date),
            'modified_date': to_iso_format(sell_order.modified_date),
            'side': -1,
            'quantity': 3,
            'price': 101,
            'filled_quantity': 0,
            'status': 1,
            'owner': dmitry.id,
            'primary_currency': sell_order.primary_currency_id,
            'secondary_currency': sell_order.secondary_currency_id,
        },
        primary_currency_id=sell_order.primary_currency_id,
        secondary_currency_id=sell_order.secondary_currency_id,
    )

    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet'),
        patch('thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order'),
    ):
        buy_order.cancel()

    assert buy_order.status == 100  # cancelled
    buy_order.refresh_from_db()
    assert buy_order.status == 100  # cancelled

    assert Wallet.objects.count() == 2
    bucky_yyy_wallet.refresh_from_db()
    assert bucky_yyy_wallet.balance == 1000  # balance reverted
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000 - 3  # balance remains unchanged

    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet'),
        patch('thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order'),
    ):
        sell_order.cancel()

    assert sell_order.status == 100  # cancelled
    sell_order.refresh_from_db()
    assert sell_order.status == 100  # cancelled

    assert Wallet.objects.count() == 2
    bucky_yyy_wallet.refresh_from_db()
    assert bucky_yyy_wallet.balance == 1000  # balance remains unchanged
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000  # balance reverted
