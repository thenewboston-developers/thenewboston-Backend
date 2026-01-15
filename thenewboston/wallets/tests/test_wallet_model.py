from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from thenewboston.general.enums import MessageType
from thenewboston.general.utils.datetime import to_iso_format


def test_wallet_change_balance(bucky_tnb_wallet):
    currency = bucky_tnb_wallet.currency

    assert bucky_tnb_wallet.balance == 1000

    with patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet') as stream_wallet_mock:
        bucky_tnb_wallet.change_balance(100)

    assert bucky_tnb_wallet.balance == 1000 + 100
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 + 100  # default persistence assertion

    stream_wallet_mock.assert_called_once_with(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data={
            'balance': 1000 + 100,
            'currency': {
                'id': bucky_tnb_wallet.currency_id,
                'owner': {
                    'avatar': None,
                    'banner': None,
                    'bio': '',
                    'connect_five_elo': None,
                    'discord_username': None,
                    'facebook_username': None,
                    'github_username': None,
                    'id': currency.owner_id,
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
                'created_date': to_iso_format(currency.created_date),
                'modified_date': to_iso_format(currency.modified_date),
                'description': None,
                'domain': 'thenewboston.net',
                'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                'ticker': 'TNB',
            },
            'created_date': to_iso_format(bucky_tnb_wallet.created_date),
            'deposit_account_number': None,
            'deposit_balance': 0,
            'id': bucky_tnb_wallet.id,
            'modified_date': to_iso_format(bucky_tnb_wallet.modified_date),
            'owner': bucky_tnb_wallet.owner_id,
        },
    )

    with patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet') as stream_wallet_mock:
        bucky_tnb_wallet.change_balance(-300)

    assert bucky_tnb_wallet.balance == 1000 + 100 - 300
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 + 100 - 300  # default persistence assertion

    stream_wallet_mock.assert_called_once_with(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data={
            'balance': 1000 + 100 - 300,
            'currency': {
                'id': bucky_tnb_wallet.currency_id,
                'owner': {
                    'avatar': None,
                    'banner': None,
                    'bio': '',
                    'connect_five_elo': None,
                    'discord_username': None,
                    'facebook_username': None,
                    'github_username': None,
                    'id': currency.owner_id,
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
                'created_date': to_iso_format(currency.created_date),
                'modified_date': to_iso_format(currency.modified_date),
                'description': None,
                'domain': 'thenewboston.net',
                'logo': 'http://localhost:8000/media/images/tnb_currency.png',
                'ticker': 'TNB',
            },
            'created_date': to_iso_format(bucky_tnb_wallet.created_date),
            'deposit_account_number': None,
            'deposit_balance': 0,
            'id': bucky_tnb_wallet.id,
            'modified_date': to_iso_format(bucky_tnb_wallet.modified_date),
            'owner': bucky_tnb_wallet.owner_id,
        },
    )

    with patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet') as stream_wallet_mock:
        bucky_tnb_wallet.change_balance(200, save=False)

    assert bucky_tnb_wallet.balance == 1000 + 100 - 300 + 200
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 + 100 - 300  # no persistence assertion

    stream_wallet_mock.assert_not_called()

    with patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet') as stream_wallet_mock:
        bucky_tnb_wallet.save(should_stream=True)

    assert bucky_tnb_wallet.balance == 1000 + 100 - 300  # balance remains unchanged
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 + 100 - 300  # no persistence assertion

    stream_wallet_mock.assert_not_called()


def test_wallet_change_balance_validation(bucky_tnb_wallet):
    assert bucky_tnb_wallet.balance == 1000

    with pytest.raises(ValidationError, match='Not enough wallet balance'):
        bucky_tnb_wallet.change_balance(-bucky_tnb_wallet.balance - 1)

    assert bucky_tnb_wallet.balance == 1000
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000  # persistence assertion
