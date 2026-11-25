from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from thenewboston.casino.fairness import FairRandom
from thenewboston.let_it_ride import engine
from thenewboston.let_it_ride.catalog import LET_IT_RIDE
from thenewboston.let_it_ride.rules import LET_IT_RIDE_V1


def fair_random(client_seed='test-client'):
    return FairRandom(
        server_seed='00' * 32,
        client_seed=client_seed,
        commitment_id='00000000-0000-0000-0000-000000000001',
        game='let_it_ride',
        rules_version=1,
    )


def hand(state, status='open'):
    return SimpleNamespace(result=state, status=status, created_date=datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc))


def test_public_fairness_vectors_replay_unchanged():
    # Published in the casino README; the browser verifier asserts the same deals.
    assert LET_IT_RIDE_V1.outcome(fair_random(), {}) == engine.initial_state(['QS', '3H', '7S'], ['TH', 'JH'])
    straight = engine.deal(fair_random('vector-0'))
    assert straight == (['KH', 'JS', 'TD'], ['QD', '9C'])
    assert engine.rank_hand([*straight[0], *straight[1]]) == 'straight'
    assert engine.deal(fair_random('vector-44')) == (['4D', '4H', '4C'], ['TH', '4S'])


@pytest.mark.parametrize('selection', [None, {}])
def test_let_it_ride_has_no_selection(selection):
    assert LET_IT_RIDE_V1.normalize_selection(selection) == {}


@pytest.mark.parametrize('selection', [[], {'bet': 1}, 'ride', 1, False])
def test_let_it_ride_rejects_selections(selection):
    with pytest.raises(ValueError, match='Let It Ride does not accept a selection.'):
        LET_IT_RIDE_V1.normalize_selection(selection)


@pytest.mark.parametrize('amount', [3, 6, 300])
def test_three_equal_bets_are_accepted(amount):
    assert LET_IT_RIDE_V1.validate_amount(amount) is None


@pytest.mark.parametrize('amount', [1, 2, 4, 100])
def test_a_wager_that_is_not_three_equal_bets_is_rejected(amount):
    with pytest.raises(ValueError, match='multiple of 3 TNB'):
        LET_IT_RIDE_V1.validate_amount(amount)


@pytest.mark.parametrize('configured,minimum', [(1, 3), (3, 3), (4, 6), (6, 6), (7, 9)])
def test_the_minimum_is_the_first_amount_that_splits_into_three_bets(configured, minimum):
    assert LET_IT_RIDE_V1.minimum_bet(configured) == minimum


def test_catalog_and_installed_math():
    LET_IT_RIDE_V1.verify()
    assert LET_IT_RIDE.default_min_bet == 3
    assert LET_IT_RIDE_V1.settlement_mode == 'interactive'
    # The casino must be able to pay three riding bets on a royal flush: 100 to 1 plus the bets themselves.
    assert LET_IT_RIDE_V1.multiplier({}) == LET_IT_RIDE_V1.max_multiplier == LET_IT_RIDE_V1.catalog_multiplier == 101
    assert LET_IT_RIDE_V1.house_edge == pytest.approx(0.0106429, abs=1e-7)
    catalog = LET_IT_RIDE_V1.catalog_data(lambda multiplier: 1000 // (multiplier - 1))
    assert catalog == {
        # 1% of a 100,000 TNB fund covers 10 TNB at 101x, rounded down to three equal bets.
        'max_bet': 9,
        'bet_increment': 3,
        'bets': 3,
        'paytable': [
            {'hand': 'royal_flush', 'odds': 100},
            {'hand': 'straight_flush', 'odds': 50},
            {'hand': 'four_of_a_kind', 'odds': 25},
            {'hand': 'full_house', 'odds': 15},
            {'hand': 'flush', 'odds': 10},
            {'hand': 'straight', 'odds': 6},
            {'hand': 'three_of_a_kind', 'odds': 3},
            {'hand': 'two_pair', 'odds': 2},
            {'hand': 'tens_or_better', 'odds': 1},
        ],
        'house_edge_per_bet': pytest.approx(0.0319288, abs=1e-7),
        'timeout_seconds': 600,
    }


def test_verification_notices_a_changed_paytable(monkeypatch):
    monkeypatch.setattr(engine, 'PAYTABLE', (('royal_flush', 1000), *engine.PAYTABLE[1:]))
    with pytest.raises(ValueError, match='paytable changed'):
        LET_IT_RIDE_V1.verify()


def test_an_open_hand_never_shows_a_card_that_is_still_face_down():
    state = engine.initial_state(['TC', 'TD', '2H'], ['3S', 'TH'])
    dealt = LET_IT_RIDE_V1.public_result(hand(state))
    assert dealt == {
        'cards': ['TC', 'TD', '2H'],
        'community': [None, None],
        'decisions': [],
        'revision': 0,
        'phase': 'first',
        'riding': 3,
        'hand': None,
        'odds': None,
        'available_actions': ['ride', 'pull'],
        'expires_at': (datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=10)).isoformat(),
    }
    state = engine.apply_action(state, 'ride', 'first-action')
    turned = LET_IT_RIDE_V1.public_result(hand(state))
    assert turned['community'] == ['3S', None]
    assert (turned['phase'], turned['revision'], turned['decisions']) == ('second', 1, ['ride'])
    state = engine.apply_action(state, 'pull', 'second-action')
    finished = LET_IT_RIDE_V1.public_result(hand(state, status='settled'))
    assert finished['community'] == ['3S', 'TH']
    assert (finished['hand'], finished['odds'], finished['riding']) == ('three_of_a_kind', 3, 2)
    assert finished['available_actions'] == [] and finished['expires_at'] is None
    assert 'action_ids' not in finished and 'action_ids' not in dealt
