"""External wallet requests must preserve concurrent game debits and credits."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from django.db import OperationalError, close_old_connections, connections, transaction
from nacl.signing import SigningKey
from rest_framework.test import APIClient

from thenewboston.general.utils.cryptography import generate_key_pair, normalize_dict
from thenewboston.wallets.models import Wallet, Wire

pytestmark = pytest.mark.django_db(transaction=True)


def request_as(user, method, url, data=None):
    close_old_connections()
    try:
        client = APIClient()
        client.force_authenticate(user)
        return getattr(client, method)(url, data, format='json')
    finally:
        connections.close_all()


def signed_wire(*, amount, recipient_account_number_str, sender_signing_key_str, **kwargs):
    key = SigningKey(bytes.fromhex(sender_signing_key_str))
    block = {
        'id': str(uuid4()),
        'amount': amount,
        'payload': {},
        'recipient': recipient_account_number_str,
        'sender': key.verify_key.encode().hex(),
        'transaction_fee': 1,
    }
    return {**block, 'signature': key.sign(normalize_dict(block)).signature.hex()}


@pytest.fixture
def external_wallet(bucky_tnb_wallet):
    keys = generate_key_pair()
    with transaction.atomic():
        bucky_tnb_wallet.deposit_account_number = keys.public
        bucky_tnb_wallet.deposit_signing_key = keys.private
        bucky_tnb_wallet.deposit_balance = 100
        bucky_tnb_wallet.save()
    return bucky_tnb_wallet


@pytest.mark.parametrize('amount', [-100, 10])
def test_deposit_balance_refresh_preserves_concurrent_game_balance(external_wallet, monkeypatch, amount):
    requested, release = Event(), Event()

    def delayed_balance(**kwargs):
        requested.set()
        assert release.wait(timeout=5)
        return 125

    monkeypatch.setattr('thenewboston.wallets.views.wallet.fetch_balance', delayed_balance)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            request_as, external_wallet.owner, 'get', f'/api/wallets/{external_wallet.id}/deposit-balance'
        )
        try:
            assert requested.wait(timeout=5)
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(pk=external_wallet.pk)
                wallet.change_balance(amount, should_stream=False)
        finally:
            release.set()
        response = future.result(timeout=10)

    assert response.status_code == 200, response.data
    external_wallet.refresh_from_db()
    assert external_wallet.balance == 1000 + amount
    assert external_wallet.deposit_balance == 125
    assert response.data['balance'] == external_wallet.balance
    assert not Wire.objects.exists()


@pytest.mark.parametrize('action', ['deposit', 'withdraw'])
def test_money_moving_request_locks_wallet_before_external_transfer(external_wallet, monkeypatch, action):
    requested, release = Event(), Event()

    def delayed_wire(**kwargs):
        requested.set()
        assert release.wait(timeout=5)
        return signed_wire(**kwargs)

    monkeypatch.setattr('thenewboston.wallets.views.wallet.wire_funds', delayed_wire)
    monkeypatch.setattr('thenewboston.wallets.views.wallet.fetch_balance', lambda **kwargs: 0)
    data = {'amount': 100, 'account_number': generate_key_pair().public} if action == 'withdraw' else {}
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            request_as, external_wallet.owner, 'post', f'/api/wallets/{external_wallet.id}/{action}', data
        )
        try:
            assert requested.wait(timeout=5)
            with pytest.raises(OperationalError), transaction.atomic():
                Wallet.objects.select_for_update(nowait=True).get(pk=external_wallet.pk)
        finally:
            release.set()
        response = future.result(timeout=10)

    assert response.status_code == 201, response.data
    external_wallet.refresh_from_db()
    assert external_wallet.balance == (900 if action == 'withdraw' else 1099)
    assert Wire.objects.count() == 1


def test_withdrawal_validates_balance_after_concurrent_game_debit(external_wallet, monkeypatch):
    requested = Event()

    def transfer(**kwargs):
        requested.set()
        return signed_wire(**kwargs)

    monkeypatch.setattr('thenewboston.wallets.views.wallet.wire_funds', transfer)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=external_wallet.pk)
            wallet.change_balance(-600, should_stream=False)
            future = executor.submit(
                request_as,
                external_wallet.owner,
                'post',
                f'/api/wallets/{external_wallet.id}/withdraw',
                {'amount': 600, 'account_number': generate_key_pair().public},
            )
            # A stale read would send money before the debit commits. The request
            # must wait for the wallet row, then reject its insufficient balance.
            assert not requested.wait(timeout=0.25)
        response = future.result(timeout=10)

    assert response.status_code == 400, response.data
    assert not requested.is_set()
    external_wallet.refresh_from_db()
    assert external_wallet.balance == 400
    assert not Wire.objects.exists()
