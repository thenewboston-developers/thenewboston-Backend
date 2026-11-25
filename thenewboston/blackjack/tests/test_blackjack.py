from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.blackjack import engine
from thenewboston.blackjack.models import BlackjackAction
from thenewboston.blackjack.services import act, expire_hand
from thenewboston.blackjack.tasks import expire_blackjack_hands
from thenewboston.casino.fairness import decrypt_seed
from thenewboston.casino.models import MAX_SAFE_INTEGER, CasinoBet, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from thenewboston.casino.services import (
    CasinoError,
    bet_receipt,
    create_commitment,
    move_funds,
    place_bet,
    reconcile_fund,
)
from thenewboston.casino.tests.test_financial_safety import accepted, race
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def treasury(bucky_tnb_wallet, monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)
    owner = bucky_tnb_wallet.owner
    owner.is_staff = True
    owner.save(update_fields=['is_staff'])
    Wallet.objects.filter(pk=bucky_tnb_wallet.pk).update(balance=200_000)
    CasinoGameConfig.objects.update_or_create(
        game='blackjack', defaults={'enabled': True, 'rules_version': 1, 'min_bet': 2}
    )
    move_funds(user=owner, amount=100_000, request_id=uuid4(), kind='deposit')
    # Player 11, dealer 17, next card ten: a double wins and a stand loses.
    monkeypatch.setattr(engine, 'shuffled_deck', lambda random: ['5C', '10H', '6S', '7D', '10C', '2D'])
    return owner


def request(user, **changes):
    commitment = create_commitment(user=user)
    return {
        'user': user,
        'request_id': uuid4(),
        'commitment_id': commitment.pk,
        'client_seed': 'blackjack-tests',
        'game': 'blackjack',
        'amount': 100,
        'rules_version': 1,
        **changes,
    }


def action(user, bet, **changes):
    return {
        'user': user,
        'request_id': bet.request_id,
        'action_id': uuid4(),
        'action': 'stand',
        'expected_revision': bet.result['revision'],
        **changes,
    }


def expire(bet):
    CasinoBet.objects.filter(pk=bet.pk).update(created_date=timezone.now() - timedelta(minutes=16))
    bet.refresh_from_db()


def test_open_hand_is_recoverable_and_never_leaks_hidden_cards_or_seed(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    payload = request(user)
    bet, _, wallet = place_bet(**payload)
    assert bet.status == 'open' and wallet.balance == 900
    assert (bet.house_exposure, bet.total_stake) == (200, 100)
    assert reconcile_fund()['reserved'] == 300
    client = APIClient()
    client.force_authenticate(user)
    responses = [
        client.get(f'/api/casino/bets/{bet.request_id}').data,
        client.get('/api/casino/bets/active').data,
        client.get('/api/casino/bets').data[0],
        bet_receipt(place_bet(**payload)[0]),
    ]
    for receipt in responses:
        assert receipt['fairness']['server_seed'] is None
        assert receipt['result']['dealer_cards'] == ['10H', None]
        assert receipt['result']['dealer_total'] == 10
        assert receipt['result']['available_actions'] == ['hit', 'stand', 'double']
        assert not {'deck', 'cursor', 'actions', 'doubled'} & receipt['result'].keys()
    client.force_authenticate(treasury)
    assert client.get('/api/casino/bets/active').content == b'null'
    assert client.get(f'/api/casino/bets/{bet.request_id}').status_code == 404
    with pytest.raises(CasinoError) as error:
        place_bet(**request(user))
    assert error.value.data['code'] == 'game_in_progress'


@pytest.mark.parametrize('amount', [1, 3, 101, 501])
def test_odd_stakes_rejected_before_any_transfer(treasury, dmitry_tnb_wallet, amount):
    with pytest.raises(CasinoError, match='even whole'):
        place_bet(**request(dmitry_tnb_wallet.owner, amount=amount))
    assert not CasinoBet.objects.exists()
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000
    assert reconcile_fund()['balance'] == 100_000


def test_catalog_reports_even_limits_and_no_false_fixed_house_edge(treasury):
    entry = next(game for game in APIClient().get('/api/casino').data['games'] if game['id'] == 'blackjack')
    assert entry['min_bet'] == entry['bet_increment'] == 2
    assert entry['max_bet'] == 500
    assert entry['house_edge'] is None
    assert entry['max_multiplier'] == 4
    assert entry['decks'] == 6


def test_odd_admin_minimum_is_rounded_to_first_playable_even_denomination(treasury):
    CasinoGameConfig.objects.filter(game='blackjack').update(min_bet=3)
    CasinoFund.objects.update(risk_limit_bps=1, balance=60_000)
    entry = next(game for game in APIClient().get('/api/casino').data['games'] if game['id'] == 'blackjack')
    assert entry['min_bet'] == 4 and entry['max_bet'] == 2
    assert not entry['available']


def test_double_adds_one_stake_and_pays_exactly_once_even_after_closure(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    payload = request(user)
    bet, _, _ = place_bet(**payload)
    CasinoFund.objects.update(enabled=False)
    CasinoGameConfig.objects.update(enabled=False)
    play = action(user, bet, action='double')
    bet, fund, wallet = act(**play)
    assert (bet.status, bet.total_stake, bet.payout, wallet.balance) == ('settled', 200, 400, 1200)
    assert bet.result['actions'] == ['double']
    assert bet.result['multiplier'] == 4
    assert fund.reserved == 0
    assert act(**play)[0].pk == bet.pk
    assert place_bet(**payload)[0].payout == 400
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='stake').count() == 2
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert BlackjackAction.objects.filter(bet=bet).count() == 1
    assert reconcile_fund()['balance'] == 99_800
    receipt = bet_receipt(bet)
    assert receipt['fairness']['server_seed'] == decrypt_seed(bet.commitment.encrypted_server_seed)
    assert receipt['result']['dealer_cards'] == ['10H', '7D']
    assert receipt['result']['available_actions'] == []


def test_double_remains_covered_after_admin_withdraws_every_free_coin(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, fund, _ = place_bet(**request(user))
    move_funds(user=treasury, amount=fund.available, request_id=uuid4(), kind='withdrawal')
    assert reconcile_fund()['balance'] == 300
    act(**action(user, bet, action='double'))
    assert reconcile_fund()['balance'] == reconcile_fund()['reserved'] == 0
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1200


@pytest.mark.parametrize(
    'cards,payout,outcome',
    [(['AS', '9C', 'KH', '8D'], 250, 'blackjack'), (['AS', 'AC', 'KH', 'KD'], 100, 'push')],
)
def test_naturals_settle_during_acceptance(treasury, dmitry_tnb_wallet, monkeypatch, cards, payout, outcome):
    monkeypatch.setattr(engine, 'shuffled_deck', lambda random: cards)
    bet, _, wallet = place_bet(**request(dmitry_tnb_wallet.owner))
    assert bet.status == 'settled' and bet.payout == payout and bet.result['outcome'] == outcome
    assert wallet.balance == 900 + payout
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert reconcile_fund()['reserved'] == 0


def test_invalid_actions_revisions_conflicts_and_other_users_never_charge(treasury, dmitry_tnb_wallet, monkeypatch):
    monkeypatch.setattr(engine, 'shuffled_deck', lambda random: ['2C', '10H', '3S', '7D', '2D', '3D'])
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    for changes in ({'action': 'split'}, {'expected_revision': True}, {'expected_revision': 1}, {'user': treasury}):
        with pytest.raises(CasinoError):
            act(**{**action(user, bet), **changes})
    play = action(user, bet, action='hit')
    bet, _, wallet = act(**play)
    assert bet.result['revision'] == 1 and bet.result['player_total'] == 7
    with pytest.raises(CasinoError) as error:
        act(**{**play, 'action': 'stand'})
    assert error.value.data['code'] == 'request_conflict'
    with pytest.raises(CasinoError) as error:
        act(**action(user, bet, action='double'))
    assert error.value.data['code'] == 'action_unavailable'
    assert wallet.balance == 900
    assert CasinoLedgerEntry.objects.filter(bet=bet).count() == 1
    assert reconcile_fund()['reserved'] == 300


def test_insufficient_double_and_action_api_validation_are_atomic(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    Wallet.objects.filter(pk=dmitry_tnb_wallet.pk).update(balance=100)
    bet, _, _ = place_bet(**request(user))
    with pytest.raises(CasinoError) as error:
        act(**action(user, bet, action='double'))
    assert error.value.data['code'] == 'insufficient_balance'
    client = APIClient()
    client.force_authenticate(user)
    payload = {'action': 'stand', 'action_id': str(uuid4()), 'expected_revision': False}
    assert client.post(f'/api/casino/bets/{bet.request_id}/actions', payload, format='json').status_code == 400
    payload['expected_revision'] = 0
    result = client.post(f'/api/casino/bets/{bet.request_id}/actions', payload, format='json')
    assert result.status_code == 200 and result.data['status'] == 'settled'
    assert client.get('/api/casino/bets/active').content == b'null'
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='stake').count() == 1
    assert reconcile_fund()['reserved'] == 0


def test_timeout_auto_stands_once_and_late_double_cannot_charge(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    expire(bet)
    bet, _, wallet = act(**action(user, bet, action='double'))
    assert bet.settlement_reason == 'timeout'
    assert bet.result['actions'] == ['stand'] and bet.payout == 0
    assert wallet.balance == 900 and bet.total_stake == 100
    assert expire_hand(bet_id=bet.pk).pk == bet.pk
    assert expire_blackjack_hands() == {'settled': 0}
    assert CasinoLedgerEntry.objects.filter(bet=bet).count() == 2
    assert reconcile_fund()['reserved'] == 0


def test_worker_only_expires_overdue_hands(treasury, dmitry_tnb_wallet):
    bet, _, _ = place_bet(**request(dmitry_tnb_wallet.owner))
    assert expire_blackjack_hands() == {'settled': 0}
    expire(bet)
    assert expire_blackjack_hands() == {'settled': 1}
    assert expire_blackjack_hands() == {'settled': 0}
    assert reconcile_fund()['reserved'] == 0


def test_corrupt_state_retains_reservation_and_is_never_rerolled(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    damaged = deepcopy(bet.result)
    damaged['player_total'] = 20
    CasinoBet.objects.filter(pk=bet.pk).update(result=damaged)
    with pytest.raises(RuntimeError, match='verification failed'):
        act(**action(user, bet, action='stand'))
    expire(bet)
    assert expire_blackjack_hands() == {'settled': 0}
    bet.refresh_from_db()
    assert bet.status == 'open' and bet.result == damaged
    assert reconcile_fund()['reserved'] == 300
    assert not BlackjackAction.objects.exists()


def test_failed_payout_ledger_rolls_back_double_stake_and_action(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    original = deepcopy(bet.result)
    create = CasinoLedgerEntry.objects.create

    def fail_payout(**kwargs):
        if kwargs['kind'] == 'payout':
            raise RuntimeError('simulated payout ledger failure')
        return create(**kwargs)

    play = action(user, bet, action='double')
    with patch.object(CasinoLedgerEntry.objects, 'create', side_effect=fail_payout):
        with pytest.raises(RuntimeError, match='simulated'):
            act(**play)
    bet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert bet.result == original and bet.total_stake == 100 and bet.status == 'open'
    assert dmitry_tnb_wallet.balance == 900
    assert not BlackjackAction.objects.exists()
    assert reconcile_fund()['reserved'] == 300
    assert act(**play)[0].payout == 400


def test_external_wallet_credit_cannot_selectively_block_only_winning_actions(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    Wallet.objects.filter(pk=dmitry_tnb_wallet.pk).update(balance=MAX_SAFE_INTEGER)
    with patch.object(engine, 'apply_action', side_effect=AssertionError('do not derive an outcome')) as derive:
        for choice in ('hit', 'stand', 'double'):
            with pytest.raises(CasinoError) as error:
                act(**action(user, bet, action=choice))
            assert error.value.data['code'] == 'wallet_limit'
        expire(bet)
        with pytest.raises(RuntimeError, match='capacity'):
            expire_hand(bet_id=bet.pk)
        derive.assert_not_called()
    assert reconcile_fund()['reserved'] == 300
    Wallet.objects.filter(pk=dmitry_tnb_wallet.pk).update(balance=900)
    assert expire_hand(bet_id=bet.pk).status == 'settled'


def test_concurrent_double_retry_charges_and_pays_once(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    play = action(user, bet, action='double')
    results = race(*[lambda: act(**play)[0].payout for _ in range(3)])
    assert results == [400, 400, 400]
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='stake').count() == 2
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert BlackjackAction.objects.filter(bet=bet).count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1200
    assert reconcile_fund()['reserved'] == 0


def test_timeout_racing_with_player_action_cannot_settle_or_charge_twice(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    expire(bet)
    race(
        lambda: accepted(lambda: act(**action(user, bet, action='double'))),
        lambda: expire_hand(bet_id=bet.pk),
    )
    bet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert bet.settlement_reason == 'timeout' and bet.result['actions'] == ['stand']
    assert bet.total_stake == 100 and dmitry_tnb_wallet.balance == 900
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert reconcile_fund()['reserved'] == 0
