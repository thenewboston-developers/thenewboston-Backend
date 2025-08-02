import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from model_bakery import baker

from thenewboston.exchange.models import ExchangeOrder, OrderProcessingLock
from thenewboston.general.clients.redis import get_redis_client
from thenewboston.general.enums import MessageType
from thenewboston.general.tests.any import ANY_INT
from thenewboston.general.tests.misc import model_to_dict_with_id
from thenewboston.general.utils.datetime import to_iso_format
from thenewboston.wallets.models.wallet import Wallet


@pytest.mark.django_db
def test_create_buy_order(authenticated_api_client, bucky, tnb_currency, yyy_currency, bucky_yyy_wallet):
    assert not ExchangeOrder.objects.exists()
    assert Wallet.objects.count() == 1
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': bucky_yyy_wallet.modified_date,
        'owner': bucky.id,
        'balance': 1000,
        'currency': yyy_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
    }

    now = timezone.now()
    trade_at = now + timedelta(minutes=10)
    OrderProcessingLock.objects.create(
        id=uuid.uuid4(), acquired_at=now - timedelta(minutes=5), trade_at=trade_at, extra={}
    )

    asset_pair = baker.make('exchange.AssetPair', primary_currency=tnb_currency, secondary_currency=yyy_currency)
    asset_pair_id = asset_pair.id
    payload = {
        'asset_pair': asset_pair_id,
        'side': 1,  # buy
        'quantity': 2,
        'price': 101
    }
    with (
        patch('thenewboston.wallets.consumers.wallet.WalletConsumer.stream_wallet') as stream_wallet_mock,
        patch('thenewboston.exchange.consumers.exchange_order.ExchangeOrderConsumer.stream_exchange_order') as
        stream_exchange_order_mock,
    ):
        response = authenticated_api_client.post('/api/exchange-orders', payload)

    response_json = response.json()
    assert (response.status_code, response_json) == (
        201, {
            'id': ANY_INT,
            'asset_pair': asset_pair_id,
            'side': 1,
            'quantity': 2,
            'price': 101,
            'status': 1,
        }
    )
    order = ExchangeOrder.objects.get(id=response_json['id'])
    after_trade_at = trade_at + timedelta(microseconds=1)
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': after_trade_at,  # timestamp adjusted to after trade_at
        'modified_date': after_trade_at,  # timestamp adjusted to after trade_at
        'owner': bucky.id,
        'asset_pair': asset_pair_id,
        'side': 1,
        'quantity': 2,
        'price': 101,
        'filled_quantity': 0,
        'status': 1,
    }

    bucky_yyy_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_yyy_wallet) == {
        'id': bucky_yyy_wallet.id,
        'created_date': bucky_yyy_wallet.created_date,
        'modified_date': after_trade_at,  # timestamp adjusted to after trade_at
        'owner': bucky.id,
        'balance': 1000 - 2 * 101,  # balance reduced by the order price
        'currency': yyy_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
    }

    stream_wallet_mock.assert_called_once_with(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data={
            'balance': 1000 - 2 * 101,
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
            'id': order.id,
            'created_date': to_iso_format(order.created_date),
            'modified_date': to_iso_format(order.modified_date),
            'side': 1,
            'quantity': 2,
            'price': 101,
            'filled_quantity': 0,
            'status': 1,
            'owner': bucky.id,
            'asset_pair': {
                'id': asset_pair_id,
                'primary_currency': {
                    'id': tnb_currency.id,
                    'ticker': tnb_currency.ticker,
                    'logo': None,
                },
                'secondary_currency': {
                    'id': yyy_currency.id,
                    'ticker': yyy_currency.ticker,
                    'logo': None,
                }
            },
        },
        primary_currency_id=order.asset_pair.primary_currency_id,
        secondary_currency_id=order.asset_pair.secondary_currency_id,
    )


@pytest.mark.django_db
def test_create_sell_order(authenticated_api_client, bucky, tnb_currency, yyy_currency, bucky_tnb_wallet):
    assert not ExchangeOrder.objects.exists()
    assert Wallet.objects.count() == 1
    assert model_to_dict_with_id(bucky_tnb_wallet) == {
        'id': bucky_tnb_wallet.id,
        'created_date': bucky_tnb_wallet.created_date,
        'modified_date': bucky_tnb_wallet.modified_date,
        'owner': bucky.id,
        'balance': 1000,
        'currency': tnb_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
    }

    now = timezone.now()
    trade_at = now + timedelta(minutes=10)
    OrderProcessingLock.objects.create(
        id=uuid.uuid4(), acquired_at=now - timedelta(minutes=5), trade_at=trade_at, extra={}
    )

    asset_pair = baker.make('exchange.AssetPair', primary_currency=tnb_currency, secondary_currency=yyy_currency)
    asset_pair_id = asset_pair.id
    payload = {
        'asset_pair': asset_pair_id,
        'side': -1,  # sell
        'quantity': 2,
        'price': 101
    }
    response = authenticated_api_client.post('/api/exchange-orders', payload)
    response_json = response.json()
    assert (response.status_code, response_json) == (
        201, {
            'id': ANY_INT,
            'asset_pair': asset_pair_id,
            'side': -1,
            'quantity': 2,
            'price': 101,
            'status': 1,
        }
    )
    order = ExchangeOrder.objects.get(id=response_json['id'])
    after_trade_at = trade_at + timedelta(microseconds=1)
    assert model_to_dict_with_id(order) == {
        'id': order.id,
        'created_date': after_trade_at,  # timestamp adjusted to after trade_at
        'modified_date': after_trade_at,  # timestamp adjusted to after trade_at
        'owner': bucky.id,
        'asset_pair': asset_pair_id,
        'side': -1,
        'quantity': 2,
        'price': 101,
        'filled_quantity': 0,
        'status': 1,
    }

    bucky_tnb_wallet.refresh_from_db()
    assert model_to_dict_with_id(bucky_tnb_wallet) == {
        'id': bucky_tnb_wallet.id,
        'created_date': bucky_tnb_wallet.created_date,
        'modified_date': after_trade_at,  # timestamp adjusted to after trade_at
        'owner': bucky.id,
        'balance': 1000 - 2,  # balance reduced by the order price
        'currency': tnb_currency.id,
        'deposit_account_number': None,
        'deposit_balance': 0,
        'deposit_signing_key': None,
    }


@pytest.mark.django_db
def test_create_order_for_someone_else(authenticated_api_client, dmitry, tnb_currency, yyy_currency, bucky_yyy_wallet):
    assert not ExchangeOrder.objects.exists()
    assert Wallet.objects.count() == 1

    asset_pair = baker.make('exchange.AssetPair', primary_currency=tnb_currency, secondary_currency=yyy_currency)
    payload = {
        'owner': dmitry.id,
        'asset_pair': asset_pair.id,
        'side': 1,  # buy
        'quantity': 2,
        'price': 101
    }
    response = authenticated_api_client.post('/api/exchange-orders', payload)
    assert (response.status_code, response.json()
            ) == (400, {
                'non_field_errors': [{
                    'message': 'Readonly field(s): owner',
                    'code': 'invalid'
                }]
            })
    assert not ExchangeOrder.objects.exists()


@pytest.mark.django_db
def test_create_order__not_enough_balance(
    authenticated_api_client, tnb_currency, yyy_currency, bucky_tnb_wallet, bucky_yyy_wallet
):
    assert not ExchangeOrder.objects.exists()

    assert bucky_yyy_wallet.balance == 1000
    asset_pair = baker.make('exchange.AssetPair', primary_currency=tnb_currency, secondary_currency=yyy_currency)
    asset_pair_id = asset_pair.id
    payload = {'asset_pair': asset_pair_id, 'side': 1, 'quantity': 1, 'price': 1001}
    response = authenticated_api_client.post('/api/exchange-orders', payload)
    assert (response.status_code, response.json()) == (
        400, {
            'non_field_errors': [{
                'message': 'Total of 1001 exceeds YYY wallet balance of 1000',
                'code': 'invalid'
            }]
        }
    )

    # We use a different balance to make sure the correct wallet is checked
    bucky_tnb_wallet.change_balance(-1)
    assert bucky_tnb_wallet.balance == 999
    payload = {'asset_pair': asset_pair_id, 'side': -1, 'quantity': 1000, 'price': 2}
    response = authenticated_api_client.post('/api/exchange-orders', payload)
    assert (response.status_code, response.json()) == (
        400, {
            'non_field_errors': [{
                'message': 'Total of 1000 exceeds TNB wallet balance of 999',
                'code': 'invalid'
            }]
        }
    )
    assert not ExchangeOrder.objects.exists()


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet')
def test_publish_new_order_message(authenticated_api_client, tnb_currency, yyy_currency):
    assert not ExchangeOrder.objects.exists()
    asset_pair = baker.make('exchange.AssetPair', primary_currency=tnb_currency, secondary_currency=yyy_currency)
    payload = {
        'asset_pair': asset_pair.id,
        'side': 1,  # buy
        'quantity': 2,
        'price': 101
    }

    pubsub = get_redis_client().pubsub()
    pubsub.subscribe('order_processing')
    for _ in range(10):  # Wait until subscription is confirmed (avoid infinite loop in case of an issue)
        message = pubsub.get_message(timeout=1)
        if message and message['type'] == 'subscribe':
            break

    try:
        response = authenticated_api_client.post('/api/exchange-orders', payload)
        assert (response.status_code, response.json(
        )) == (201, {
            'id': ANY_INT,
            'asset_pair': ANY_INT,
            'side': 1,
            'quantity': 2,
            'price': 101,
            'status': 1
        })
        message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
        assert message
        assert message.get('type') == 'message' and message.get('data') == 'new_order'
    finally:
        pubsub.unsubscribe()
        pubsub.close()
