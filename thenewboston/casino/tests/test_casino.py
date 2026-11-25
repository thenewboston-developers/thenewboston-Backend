from collections import Counter
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib import admin
from django.core.management import call_command
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from thenewboston.casino.admin import CasinoFundAdmin
from thenewboston.casino.fairness import FairRandom, seed_hash
from thenewboston.casino.models import CasinoBet, CasinoCommitment, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from thenewboston.casino.rules import ROULETTE_TYPES, RULES, SLOT_WEIGHTS
from thenewboston.casino.services import (
    CasinoError,
    create_commitment,
    move_funds,
    place_bet,
    reconcile_fund,
    settle_bet,
)
from thenewboston.game_rewards.models import GameFund

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def configs():
    for game in ('slots', 'roulette'):
        CasinoGameConfig.objects.get_or_create(game=game)


@pytest.fixture
def funded(bucky_tnb_wallet):
    wallet = bucky_tnb_wallet
    wallet.owner.is_staff = True
    wallet.owner.save(update_fields=['is_staff'])
    wallet.balance = 200000
    wallet.save(should_adjust_timestamps=False)
    move_funds(user=wallet.owner, amount=100000, request_id=uuid4(), kind='deposit')
    return wallet.owner


def wager(user, **changes):
    commitment = create_commitment(user=user)
    return {
        'user': user,
        'request_id': uuid4(),
        'commitment_id': commitment.id,
        'client_seed': 'test-client',
        'game': 'slots',
        'amount': 10,
        'rules_version': 1,
        **changes,
    }


def test_summary_read_only_and_separate_from_board_game_fund():
    CasinoFund.objects.all().delete()
    board_fund = GameFund.objects.create(balance=999, total_deposited=999)
    client = APIClient()
    response = client.get('/api/casino')
    assert response.status_code == 200
    assert response.data['fund']['balance'] == response.data['fund']['reserved'] == 0
    assert not response.data['can_manage']
    assert not any(game['available'] for game in response.data['games'])
    assert not CasinoFund.objects.exists()
    board_fund.refresh_from_db()
    assert board_fund.balance == 999
    assert client.post('/api/casino/commitments', {}, format='json').status_code == 401


def test_funding_is_admin_only_atomic_idempotent_and_reconciled(bucky_tnb_wallet):
    user = bucky_tnb_wallet.owner
    request_id = uuid4()
    with pytest.raises(CasinoError) as error:
        move_funds(user=user, amount=100, request_id=request_id, kind='deposit')
    assert error.value.status == 403
    user.is_staff = True
    first, _, _ = move_funds(user=user, amount=100, request_id=request_id, kind='deposit')
    again, _, _ = move_funds(user=user, amount=100, request_id=request_id, kind='deposit')
    assert first.pk == again.pk
    with pytest.raises(CasinoError) as conflict:
        move_funds(user=user, amount=100, request_id=request_id, kind='withdrawal')
    assert conflict.value.status == 409
    assert reconcile_fund()['ledger_balance'] == 100
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900


def test_limits_at_one_hundred_thousand(funded):
    data = APIClient().get('/api/casino').data
    slots, roulette = data['games']
    assert slots['max_bet'] == 10
    assert slots['max_multiplier'] == 100
    types = {item['id']: item['max_bet'] for item in roulette['bet_types']}
    assert types['red'] == 1000
    assert types['number'] == 28
    assert types['dozen'] == 500
    with pytest.raises(CasinoError) as error:
        place_bet(**wager(funded, amount=11))
    assert error.value.data['max_bet'] == 10
    assert not CasinoBet.objects.exists()
    assert reconcile_fund()['balance'] == 100000


def test_bet_replay_and_settlement_are_once_even_after_closure(funded):
    payload = wager(funded)
    first, _, wallet = place_bet(**payload)
    expected_balance = wallet.balance
    CasinoFund.objects.filter(pk=1).update(enabled=False)
    second, _, wallet = place_bet(**payload)
    assert first.id == second.id
    assert wallet.balance == expected_balance
    assert settle_bet(bet_id=first.id).id == first.id
    assert CasinoLedgerEntry.objects.filter(bet=first).count() == 2
    assert reconcile_fund()['reserved'] == 0
    with pytest.raises(CasinoError) as error:
        place_bet(**{**payload, 'amount': 9})
    assert error.value.status == 409


@pytest.mark.parametrize('amount', [True, False, '10', 1.0, 1.5, -1, 0, 1000000001])
def test_api_rejects_non_integer_or_invalid_stakes_before_charge(funded, amount):
    client = APIClient()
    client.force_authenticate(funded)
    payload = wager(funded, amount=amount)
    del payload['user']
    response = client.post('/api/casino/bets', payload, format='json')
    assert response.status_code == 400
    assert not CasinoBet.objects.exists()
    assert reconcile_fund()['balance'] == 100000


@pytest.mark.parametrize(
    'selection',
    [
        {'type': []},
        {'type': {}},
        {'type': 'number', 'value': True},
        {'type': 'number', 'value': 37},
        {'type': 'red', 'value': 1},
        [],
    ],
)
def test_invalid_roulette_selection_is_clean_rejection(funded, selection):
    with pytest.raises(CasinoError):
        place_bet(**wager(funded, game='roulette', selection=selection))
    assert not CasinoBet.objects.exists()


def test_commitment_is_private_single_use_and_owner_scoped(funded, dmitry):
    client = APIClient()
    client.force_authenticate(funded)
    response = client.post('/api/casino/commitments', {}, format='json')
    assert set(response.data) == {'id', 'server_seed_hash', 'expires_at', 'algorithm'}
    commitment = CasinoCommitment.objects.get(pk=response.data['id'])
    assert create_commitment(user=funded).id == commitment.id
    with pytest.raises(CasinoError):
        place_bet(**wager(dmitry, commitment_id=commitment.id))
    bet, _, _ = place_bet(**wager(funded, commitment_id=commitment.id))
    assert seed_hash(bet.revealed_server_seed) == response.data['server_seed_hash']
    with pytest.raises(CasinoError):
        place_bet(**wager(funded, commitment_id=commitment.id))
    client.force_authenticate(dmitry)
    assert client.get(f'/api/casino/bets/{bet.request_id}').status_code == 404
    assert client.get('/api/casino/bets').data == []


def test_history_and_recovery_supply_verifiable_receipt(funded):
    client = APIClient()
    client.force_authenticate(funded)
    payload = wager(funded, game='roulette', selection={'type': 'number', 'value': 0})
    del payload['user']
    response = client.post('/api/casino/bets', payload, format='json')
    assert response.status_code == 201
    receipt = response.data
    assert receipt['status'] == 'settled'
    assert receipt['fairness']['server_seed']
    assert client.get(f'/api/casino/bets/{receipt["request_id"]}').data['result'] == receipt['result']
    assert client.get('/api/casino/bets').data[0]['id'] == receipt['id']
    assert client.get('/api/casino').data['can_manage']


class FixedRandom:
    def __init__(self, value):
        self.value = value

    def below(self, bound):
        assert self.value < bound
        return self.value


def test_slots_exhaustive_probabilities_rtp_and_cap():
    counts = Counter(RULES[('slots', 1)].outcome(FixedRandom(draw), {})['multiplier'] for draw in range(10000))
    assert dict(counts) == dict(SLOT_WEIGHTS)
    assert sum(multiplier * count for multiplier, count in counts.items()) == 9600
    assert max(counts) == 100


@pytest.mark.parametrize('kind', ROULETTE_TYPES)
def test_roulette_exhaustive_rtp_and_zero(kind):
    selection = {'type': kind}
    if kind in ('number', 'dozen', 'column'):
        selection['value'] = 0 if kind == 'number' else 1
    outcomes = [RULES[('roulette', 1)].outcome(FixedRandom(number), selection) for number in range(37)]
    assert sum(result['multiplier'] for result in outcomes) == 36
    assert outcomes[0]['color'] == 'green'
    assert outcomes[0]['multiplier'] == (36 if kind == 'number' else 0)


def test_random_rejects_biased_upper_tail():
    rejected = (2**64 - 1).to_bytes(8, 'big') + bytes(24)
    accepted = (38).to_bytes(8, 'big') + bytes(24)
    random = FairRandom(
        server_seed='01' * 32, client_seed='client', commitment_id=uuid4(), game='roulette', rules_version=1
    )
    with patch('thenewboston.casino.fairness.hmac.new') as digest:
        digest.return_value.digest.side_effect = [rejected, accepted]
        assert random.below(37) == 1
    assert random.counter == 2


def test_database_rejects_uncovered_reservation_and_admin_does_not_overwrite_balance(funded):
    fund = CasinoFund.objects.get(pk=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        CasinoFund.objects.filter(pk=1).update(reserved=100001)
    stale = CasinoFund.objects.get(pk=1)
    move_funds(user=funded, amount=100, request_id=uuid4(), kind='deposit')
    stale.enabled = False
    CasinoFundAdmin(CasinoFund, admin.site).save_model(None, stale, None, True)
    fund.refresh_from_db()
    assert fund.balance == 100100
    assert not fund.enabled
    assert reconcile_fund()['ledger_balance'] == 100100


def test_read_only_management_verification(funded):
    before = CasinoLedgerEntry.objects.count()
    output = StringIO()
    call_command('verify_casino', stdout=output)
    assert 'Casino verified' in output.getvalue()
    assert CasinoLedgerEntry.objects.count() == before
