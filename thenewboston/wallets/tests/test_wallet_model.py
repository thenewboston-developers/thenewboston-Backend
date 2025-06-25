from unittest.mock import patch

import pytest

from thenewboston.general.enums import MessageType
from thenewboston.general.exceptions import ThenewbostonValueError
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
                    'id': currency.owner_id,
                    'username': 'bucky',
                    'is_staff': False
                },
                'created_date': to_iso_format(currency.created_date),
                'modified_date': to_iso_format(currency.modified_date),
                'description': None,
                'domain': 'thenewboston.net',
                'logo': None,
                'ticker': 'TNB'
            },
            'created_date': to_iso_format(bucky_tnb_wallet.created_date),
            'deposit_account_number': None,
            'deposit_balance': 0,
            'id': bucky_tnb_wallet.id,
            'modified_date': to_iso_format(bucky_tnb_wallet.modified_date),
            'owner': bucky_tnb_wallet.owner_id,
        }
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
                    'id': currency.owner_id,
                    'username': 'bucky',
                    'is_staff': False
                },
                'created_date': to_iso_format(currency.created_date),
                'modified_date': to_iso_format(currency.modified_date),
                'description': None,
                'domain': 'thenewboston.net',
                'logo': None,
                'ticker': 'TNB'
            },
            'created_date': to_iso_format(bucky_tnb_wallet.created_date),
            'deposit_account_number': None,
            'deposit_balance': 0,
            'id': bucky_tnb_wallet.id,
            'modified_date': to_iso_format(bucky_tnb_wallet.modified_date),
            'owner': bucky_tnb_wallet.owner_id,
        }
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

    with pytest.raises(ThenewbostonValueError, match='New balance cannot be negative'):
        bucky_tnb_wallet.change_balance(-bucky_tnb_wallet.balance - 1)

    assert bucky_tnb_wallet.balance == 1000
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000  # persistence assertion
