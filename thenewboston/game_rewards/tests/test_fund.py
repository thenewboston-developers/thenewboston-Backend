from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from thenewboston.game_rewards.models import GameFund, GameFundDeposit, GameRewardDecision
from thenewboston.game_rewards.services import contribute, fund_summary, settle_computer_reward
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db


def test_public_empty_summary_is_read_only_and_deposits_require_authentication():
    client = APIClient()
    response = client.get('/api/game-fund')
    assert response.status_code == 200
    assert response.data == dict(
        balance=0,
        currency='TNB',
        reward_amount=10,
        wins_remaining=0,
        total_deposited=0,
        total_paid=0,
        enabled=True,
        available=False,
    )
    assert GameFund.objects.count() == 0
    assert client.post('/api/game-fund/deposits', {'amount': 10, 'request_id': str(uuid4())}).status_code == 401


@pytest.mark.parametrize('amount', [0, -1, 1.5, 1000000001, True, 'bad'])
def test_bad_contribution_cannot_charge(bucky_tnb_wallet, amount):
    client = APIClient()
    client.force_authenticate(bucky_tnb_wallet.owner)
    response = client.post('/api/game-fund/deposits', {'amount': amount, 'request_id': str(uuid4())})
    assert response.status_code == 400
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert GameFundDeposit.objects.count() == 0


def test_deposit_retry_is_exactly_once_and_changed_amount_conflicts(bucky_tnb_wallet):
    client = APIClient()
    client.force_authenticate(bucky_tnb_wallet.owner)
    payload = {'amount': 35, 'request_id': str(uuid4())}
    first = client.post('/api/game-fund/deposits', payload)
    retry = client.post('/api/game-fund/deposits', payload)
    assert first.status_code == retry.status_code == 201
    assert first.data['id'] == retry.data['id']
    assert first.data['fund']['wins_remaining'] == 3
    assert client.post('/api/game-fund/deposits', {**payload, 'amount': 45}).status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 965
    assert GameFundDeposit.objects.count() == 1
    assert fund_summary()['balance'] == 35


def test_insufficient_balance_and_missing_wallet_are_atomic(bucky_tnb_wallet, dmitry):
    client = APIClient()
    client.force_authenticate(bucky_tnb_wallet.owner)
    assert client.post('/api/game-fund/deposits', {'amount': 1001, 'request_id': str(uuid4())}).status_code == 400
    client.force_authenticate(dmitry)
    assert client.post('/api/game-fund/deposits', {'amount': 1, 'request_id': str(uuid4())}).status_code == 400
    assert GameFundDeposit.objects.count() == 0
    assert GameFund.objects.count() == 0


def test_rewards_conserve_money_and_stop_below_ten(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=25, request_id=uuid4())
    for match_id in (1, 2):
        result = settle_computer_reward(
            game='battleship', match_id=match_id, user_id=dmitry_tnb_wallet.owner_id, won=True
        )
        assert result == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
        assert (
            settle_computer_reward(game='battleship', match_id=match_id, user_id=dmitry_tnb_wallet.owner_id, won=True)
            == result
        )
    assert (
        settle_computer_reward(game='backgammon', match_id=1, user_id=dmitry_tnb_wallet.owner_id, won=True)['status']
        == 'fund_empty'
    )
    fund = GameFund.objects.get()
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (fund.balance, fund.total_deposited, fund.total_paid) == (5, 25, 20)
    assert bucky_tnb_wallet.balance + dmitry_tnb_wallet.balance + fund.balance == 2000
    assert GameRewardDecision.objects.filter(status='paid').count() == 2


def test_topups_never_retroactively_reward_empty_or_ineligible_matches(bucky_tnb_wallet, dmitry):
    for match_id, won in [(1, True), (2, False)]:
        settle_computer_reward(game='backgammon', match_id=match_id, user_id=dmitry.id, won=won)
    contribute(user=bucky_tnb_wallet.owner, amount=20, request_id=uuid4())
    assert settle_computer_reward(game='backgammon', match_id=1, user_id=dmitry.id, won=True)['status'] == 'fund_empty'
    assert (
        settle_computer_reward(game='backgammon', match_id=2, user_id=dmitry.id, won=True)['status'] == 'not_eligible'
    )
    assert fund_summary()['balance'] == 20
    assert not Wallet.objects.filter(owner=dmitry).exists()


def test_winner_wallet_creation_preserves_external_currency_keys(bucky_tnb_wallet, dmitry):
    assert bucky_tnb_wallet.currency.domain
    contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=uuid4())
    settle_computer_reward(game='connect_five', match_id=1, user_id=dmitry.id, won=True)
    wallet = Wallet.objects.get(owner=dmitry, currency=bucky_tnb_wallet.currency)
    assert wallet.balance == 10
    assert wallet.deposit_account_number and wallet.deposit_signing_key


def test_pause_keeps_free_game_completion_and_topups_safe(bucky_tnb_wallet, dmitry):
    contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=uuid4())
    GameFund.objects.filter(pk=1).update(enabled=False)
    result = settle_computer_reward(game='battleship', match_id=1, user_id=dmitry.id, won=True)
    assert result['amount'] == 0
    assert not fund_summary()['available']
    assert fund_summary()['balance'] == 10


def test_failed_outer_game_transaction_rolls_back_payout_and_decision(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=uuid4())
    with pytest.raises(RuntimeError), transaction.atomic():
        settle_computer_reward(game='battleship', match_id=1, user_id=dmitry_tnb_wallet.owner_id, won=True)
        raise RuntimeError('game could not commit')
    assert GameRewardDecision.objects.count() == 0
    assert fund_summary()['balance'] == 10
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000


def test_broadcast_failure_cannot_turn_committed_deposit_into_retry_charge(bucky_tnb_wallet):
    request_id = uuid4()
    with patch.object(Wallet, 'stream', side_effect=RuntimeError('redis unavailable')):
        deposit, _ = contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=request_id)
        retry, _ = contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=request_id)
    assert deposit.id == retry.id
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 990
