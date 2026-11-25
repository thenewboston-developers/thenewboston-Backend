"""Roulette rules version 2 through the shared treasury: one spin settles chips on several spots."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from thenewboston.casino.fairness import FairRandom, seed_hash
from thenewboston.casino.models import CasinoBet, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from thenewboston.casino.services import CasinoError, create_commitment, move_funds, place_bet, reconcile_fund
from thenewboston.roulette.rules import ROULETTE_V2
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def roulette_version_2():
    CasinoGameConfig.objects.update_or_create(game='roulette', defaults={'enabled': True, 'rules_version': 2})


@pytest.fixture
def player(bucky_tnb_wallet):
    wallet = bucky_tnb_wallet
    wallet.owner.is_staff = True
    wallet.owner.save(update_fields=['is_staff'])
    wallet.balance = 200000
    wallet.save(should_adjust_timestamps=False)
    move_funds(user=wallet.owner, amount=100000, request_id=uuid4(), kind='deposit')
    return wallet.owner


def spin(user, bets, **changes):
    commitment = create_commitment(user=user)
    return {
        'user': user,
        'request_id': uuid4(),
        'commitment_id': commitment.id,
        'client_seed': 'table-client',
        'game': 'roulette',
        'amount': sum(bet['amount'] for bet in bets),
        'rules_version': 2,
        'selection': {'bets': bets},
        **changes,
    }


def balance(user):
    return Wallet.objects.get(owner=user, currency__ticker='TNB').balance


MIXED = [
    {'type': 'number', 'value': 17, 'amount': 2},
    {'type': 'red', 'amount': 10},
    {'type': 'dozen', 'value': 2, 'amount': 6},
    {'type': 'odd', 'amount': 4},
    {'type': 'column', 'value': 2, 'amount': 3},
]


def test_migration_selects_version_2_and_the_catalog_says_so(player):
    roulette = APIClient().get('/api/casino').data['games'][1]
    assert roulette['id'] == 'roulette'
    assert roulette['rules_version'] == 2
    assert roulette['multiple_bets'] is True
    assert {item['id']: item['max_bet'] for item in roulette['bet_types']} == {
        'red': 1000,
        'black': 1000,
        'odd': 1000,
        'even': 1000,
        'low': 1000,
        'high': 1000,
        'dozen': 500,
        'column': 500,
        'number': 28,
    }


def test_one_spin_settles_every_bet_and_keeps_the_books_balanced(player):
    before = balance(player)
    bet, fund, wallet = place_bet(**spin(player, MIXED))
    assert bet.status == 'settled'
    assert bet.amount == bet.total_stake == 25
    # The worst case for the casino is 17: it pays 107 against the 25 staked.
    assert bet.house_exposure == 82
    number = bet.result['number']
    expected = ROULETTE_V2.returned(bet.selection, number)
    assert bet.result == {'number': number, 'color': bet.result['color'], 'payout': expected}
    assert bet.payout == expected
    assert wallet.balance == balance(player) == before - 25 + expected
    assert fund.balance == 100000 + 25 - expected
    assert fund.reserved == 0
    assert list(CasinoLedgerEntry.objects.filter(bet=bet).order_by('id').values_list('kind', 'amount')) == [
        ('stake', 25),
        ('payout', expected),
    ]
    assert reconcile_fund() == {
        'balance': fund.balance,
        'reserved': 0,
        'ledger_balance': fund.balance,
        'expected_reserved': 0,
        'open_bets': 0,
    }


def test_the_receipt_reproduces_from_the_revealed_seed(player):
    bet, _, _ = place_bet(**spin(player, MIXED))
    assert seed_hash(bet.revealed_server_seed) == bet.commitment.server_seed_hash
    random = FairRandom(
        server_seed=bet.revealed_server_seed,
        client_seed=bet.client_seed,
        commitment_id=bet.commitment_id,
        game='roulette',
        rules_version=2,
    )
    assert ROULETTE_V2.outcome(random, bet.selection) == bet.result
    # Stored in table order, each bet with its own stake.
    assert [(item['type'], item.get('value'), item['amount']) for item in bet.selection['bets']] == [
        ('red', None, 10),
        ('odd', None, 4),
        ('dozen', 2, 6),
        ('column', 2, 3),
        ('number', 17, 2),
    ]


def test_the_limit_is_the_worst_case_of_the_whole_table(player):
    # 100,000 TNB at a 1% risk limit lets one wager cost the casino 1,000 TNB.
    straight = [{'type': 'number', 'value': 7, 'amount': 28}]
    assert place_bet(**spin(player, straight))[0].house_exposure == 980
    with pytest.raises(CasinoError) as error:
        place_bet(**spin(player, [{'type': 'number', 'value': 7, 'amount': 29}]))
    assert error.value.data['code'] == 'bet_limit'
    assert error.value.data['max_bet'] == 28
    # Two bets that win together are judged together: 20 on 8 and 400 on black would cost 1,100 on 8.
    with pytest.raises(CasinoError) as error:
        place_bet(**spin(player, [{'type': 'number', 'value': 8, 'amount': 20}, {'type': 'black', 'amount': 400}]))
    assert error.value.data['code'] == 'bet_limit'
    CasinoFund.objects.filter(pk=1).update(balance=100000)
    # Two bets that cannot win together are not: 28 on a red number and 900 on black never pay on the same spin.
    apart = [{'type': 'number', 'value': 7, 'amount': 28}, {'type': 'black', 'amount': 900}]
    assert place_bet(**spin(player, apart))[0].house_exposure == 872
    assert not CasinoBet.objects.filter(status='open').exists()


def test_a_fully_hedged_table_is_accepted_even_when_the_fund_can_risk_nothing(player):
    CasinoFund.objects.filter(pk=1).update(risk_limit_bps=1)
    fund = CasinoFund.objects.get(pk=1)
    CasinoFund.objects.filter(pk=1).update(balance=9999)
    assert CasinoFund.objects.get(pk=1).available * fund.risk_limit_bps // 10000 == 0
    hedged = [{'type': 'red', 'amount': 50}, {'type': 'black', 'amount': 50}]
    bet, _, _ = place_bet(**spin(player, hedged))
    assert bet.house_exposure == 0
    assert bet.payout in (0, 100)
    with pytest.raises(CasinoError) as error:
        place_bet(**spin(player, [{'type': 'red', 'amount': 1}]))
    assert error.value.data['code'] == 'bet_limit'


def test_rejections_charge_nothing(player):
    before = balance(player)
    with pytest.raises(CasinoError, match='add up'):
        place_bet(**spin(player, MIXED, amount=26))
    with pytest.raises(CasinoError, match='one bet'):
        place_bet(**spin(player, [{'type': 'red', 'amount': 2}, {'type': 'red', 'amount': 3}]))
    with pytest.raises(CasinoError, match='at least one'):
        place_bet(**spin(player, [], amount=5))
    with pytest.raises(CasinoError) as error:
        place_bet(**spin(player, [{'type': 'red', 'amount': 150000}, {'type': 'black', 'amount': 150000}]))
    assert error.value.data['code'] == 'insufficient_balance'
    assert balance(player) == before
    assert not CasinoBet.objects.exists()
    assert reconcile_fund()['balance'] == 100000


def test_a_table_from_before_version_2_still_plays_its_single_spot(player):
    request = spin(player, [], amount=5, selection={'type': 'number', 'value': 0})
    bet, _, _ = place_bet(**request)
    assert bet.selection == {'bets': [{'type': 'number', 'value': 0, 'amount': 5}]}
    assert bet.house_exposure == 175
    assert bet.payout == (180 if bet.result['number'] == 0 else 0)
    # Replaying the same request returns the same bet.
    again, _, _ = place_bet(**request)
    assert again.pk == bet.pk


def test_a_replay_is_the_same_bet_whatever_order_the_chips_arrive_in(player):
    request = spin(player, MIXED)
    first, _, _ = place_bet(**request)
    again, _, _ = place_bet(**{**request, 'selection': {'bets': list(reversed(MIXED))}})
    assert again.pk == first.pk
    assert CasinoBet.objects.count() == 1
    different = [{**MIXED[0], 'amount': 3}, {**MIXED[1], 'amount': 9}, *MIXED[2:]]
    with pytest.raises(CasinoError) as conflict:
        place_bet(**{**request, 'selection': {'bets': different}})
    assert conflict.value.status == 409


def test_version_1_requests_are_refused_once_version_2_is_selected(player):
    with pytest.raises(CasinoError) as error:
        place_bet(**spin(player, [], amount=5, selection={'type': 'red'}, rules_version=1))
    assert error.value.data['code'] == 'rules_changed'


def test_the_api_accepts_a_table_and_returns_its_receipt(player):
    client = APIClient()
    client.force_authenticate(player)
    commitment = client.post('/api/casino/commitments', {}, format='json').data
    payload = {
        'amount': 25,
        'client_seed': 'browser-seed',
        'commitment_id': commitment['id'],
        'game': 'roulette',
        'request_id': str(uuid4()),
        'rules_version': 2,
        'selection': {'bets': MIXED},
    }
    response = client.post('/api/casino/bets', payload, format='json')
    assert response.status_code == 201
    receipt = response.data
    assert receipt['status'] == 'settled'
    assert receipt['amount'] == receipt['total_stake'] == 25
    assert receipt['payout'] == receipt['result']['payout']
    assert receipt['profit'] == receipt['payout'] - 25
    assert len(receipt['selection']['bets']) == 5
    assert client.get(f'/api/casino/bets/{payload["request_id"]}').data['result'] == receipt['result']
    bad = client.post(
        '/api/casino/bets',
        {**payload, 'request_id': str(uuid4()), 'selection': {'bets': [{'type': 'red', 'amount': 2.5}]}},
        format='json',
    )
    assert bad.status_code == 400
