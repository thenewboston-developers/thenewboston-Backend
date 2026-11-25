import hashlib
import json

import pytest

from thenewboston.casino.fairness import FairRandom
from thenewboston.roulette.rules import ROULETTE_V1, ROULETTE_V2

SELECTIONS = (
    [{'type': kind} for kind in ('red', 'black', 'odd', 'even', 'low', 'high')]
    + [{'type': kind, 'value': value} for kind in ('dozen', 'column') for value in range(1, 4)]
    + [{'type': 'number', 'value': value} for value in range(37)]
)


class FixedRandom:
    def __init__(self, value):
        self.value = value

    def below(self, bound):
        assert bound == 37
        return self.value


def test_all_version_one_outcomes_are_identical_to_the_original_casino_implementation():
    outcomes = [
        {
            'selection': selection,
            'outcomes': [ROULETTE_V1.outcome(FixedRandom(number), selection) for number in range(37)],
        }
        for selection in SELECTIONS
    ]
    # Every number for every supported selection, captured before extracting the game app.
    fingerprint = hashlib.sha256(json.dumps(outcomes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert fingerprint == 'f56c04f047fc13c759ba43519faa48120a5161ff95b6209d1c2457c7aa3987b1'


@pytest.mark.parametrize('selection', SELECTIONS)
def test_every_selection_has_the_same_return_and_zero_behavior(selection):
    assert ROULETTE_V1.normalize_selection(selection) == selection
    outcomes = [ROULETTE_V1.outcome(FixedRandom(number), selection) for number in range(37)]
    assert sum(result['multiplier'] for result in outcomes) == 36
    assert outcomes[0]['color'] == 'green'
    assert outcomes[0]['multiplier'] == (36 if selection == {'type': 'number', 'value': 0} else 0)
    assert max(result['multiplier'] for result in outcomes) == ROULETTE_V1.multiplier(selection)


@pytest.mark.parametrize(
    'selection',
    [
        None,
        [],
        {},
        {'type': []},
        {'type': {}},
        {'type': 'number', 'value': True},
        {'type': 'number', 'value': -1},
        {'type': 'number', 'value': 37},
        {'type': 'number', 'value': 1.0},
        {'type': 'dozen', 'value': 0},
        {'type': 'column', 'value': 4},
        {'type': 'red', 'value': 1},
        {'type': 'red', 'unexpected': 'value'},
    ],
)
def test_roulette_rejects_invalid_selections(selection):
    with pytest.raises(ValueError):
        ROULETTE_V1.normalize_selection(selection)


def test_version_one_fairness_receipt_replays_unchanged():
    random = FairRandom(
        server_seed='01' * 32,
        client_seed='characterization',
        commitment_id='00000000-0000-0000-0000-000000000001',
        game='roulette',
        rules_version=1,
    )
    assert ROULETTE_V1.outcome(random, {'type': 'red'}) == {'number': 12, 'color': 'red', 'multiplier': 2}


def test_roulette_catalog_and_installed_math():
    ROULETTE_V1.verify()
    assert ROULETTE_V1.catalog_multiplier == 2
    assert ROULETTE_V1.catalog_data(lambda multiplier: 1000 // (multiplier - 1)) == {
        'bet_types': [
            {'id': 'red', 'label': 'Red', 'multiplier': 2, 'max_bet': 1000},
            {'id': 'black', 'label': 'Black', 'multiplier': 2, 'max_bet': 1000},
            {'id': 'odd', 'label': 'Odd', 'multiplier': 2, 'max_bet': 1000},
            {'id': 'even', 'label': 'Even', 'multiplier': 2, 'max_bet': 1000},
            {'id': 'low', 'label': '1–18', 'multiplier': 2, 'max_bet': 1000},
            {'id': 'high', 'label': '19–36', 'multiplier': 2, 'max_bet': 1000},
            {'id': 'dozen', 'label': 'Dozen', 'multiplier': 3, 'max_bet': 500},
            {'id': 'column', 'label': 'Column', 'multiplier': 3, 'max_bet': 500},
            {'id': 'number', 'label': 'Single number', 'multiplier': 36, 'max_bet': 28},
        ]
    }


def table(*bets):
    return {'bets': [dict(zip(('type', 'amount', 'value'), bet)) for bet in bets]}


def test_version_one_stays_the_default_free_implementation():
    # Version 2 subclasses version 1; the original must keep its own selection, outcome and payout behavior.
    assert ROULETTE_V1.prepare_selection({'type': 'red'}, 7) == {'type': 'red'}
    assert ROULETTE_V1.exposure({'type': 'number', 'value': 3}, 7) == 35 * 7
    assert ROULETTE_V1.payout(7, {'multiplier': 36}) == 252
    assert 'multiple_bets' not in ROULETTE_V1.catalog_data(lambda multiplier: 1)


@pytest.mark.parametrize('selection', SELECTIONS)
def test_a_single_version_two_bet_pays_exactly_what_version_one_pays(selection):
    prepared = ROULETTE_V2.prepare_selection({'bets': [{**selection, 'amount': 5}]}, 5)
    assert prepared == {'bets': [{**selection, 'amount': 5}]}
    # A table that predates version 2 sends the single spot on its own.
    assert ROULETTE_V2.prepare_selection(selection, 5) == prepared
    for number in range(37):
        original = ROULETTE_V1.outcome(FixedRandom(number), selection)
        result = ROULETTE_V2.outcome(FixedRandom(number), prepared)
        assert result == {'number': number, 'color': original['color'], 'payout': 5 * original['multiplier']}
        assert ROULETTE_V2.payout(5, result) == ROULETTE_V1.payout(5, original)
    assert ROULETTE_V2.exposure(prepared, 5) == ROULETTE_V1.exposure(selection, 5)
    assert ROULETTE_V2.multiplier(prepared) == ROULETTE_V1.multiplier(selection)


def test_several_bets_pay_the_sum_of_their_winners():
    selection = ROULETTE_V2.prepare_selection(
        table(('number', 2, 17), ('red', 10), ('dozen', 6, 2), ('odd', 4), ('column', 3, 2)), 25
    )
    # 17 is black, odd, in the second dozen and the second column.
    assert ROULETTE_V2.outcome(FixedRandom(17), selection) == {
        'number': 17,
        'color': 'black',
        'payout': 2 * 36 + 6 * 3 + 4 * 2 + 3 * 3,
    }
    # 14 is red and in the second dozen and column; zero pays none of these bets.
    assert ROULETTE_V2.outcome(FixedRandom(14), selection)['payout'] == 10 * 2 + 6 * 3 + 3 * 3
    assert ROULETTE_V2.outcome(FixedRandom(0), selection) == {'number': 0, 'color': 'green', 'payout': 0}
    assert ROULETTE_V2.multiplier(selection) == 36
    # The casino's worst case is 17: everything it pays, less the 25 staked.
    assert ROULETTE_V2.exposure(selection, 25) == 107 - 25


def test_every_combination_of_bets_keeps_the_house_edge():
    selection = ROULETTE_V2.prepare_selection(
        table(('number', 3, 0), ('number', 1, 36), ('black', 20), ('high', 7), ('dozen', 5, 1), ('column', 9, 3)), 45
    )
    assert sum(ROULETTE_V2.returned(selection, number) for number in range(37)) == 45 * 36


def test_bets_that_cover_each_other_lower_the_exposure():
    assert ROULETTE_V2.exposure(ROULETTE_V2.prepare_selection(table(('red', 100)), 100), 100) == 100
    hedged = ROULETTE_V2.prepare_selection(table(('red', 100), ('black', 100)), 200)
    assert ROULETTE_V2.exposure(hedged, 200) == 0
    every_number = ROULETTE_V2.prepare_selection(table(*(('number', 1, value) for value in range(37))), 37)
    # 36 of 37 chips come back whatever lands: the casino cannot lose, and exposure is never negative.
    assert {ROULETTE_V2.returned(every_number, number) for number in range(37)} == {36}
    assert ROULETTE_V2.exposure(every_number, 37) == 0
    assert ROULETTE_V2.returned(hedged, 0) == 0
    assert {ROULETTE_V2.returned(hedged, number) for number in range(1, 37)} == {200}


def test_bets_are_stored_in_table_order_whatever_order_they_were_placed_in():
    placed = table(('number', 1, 5), ('black', 2), ('column', 3, 1), ('number', 4, 0), ('red', 5), ('dozen', 6, 3))
    reordered = {'bets': list(reversed(placed['bets']))}
    assert ROULETTE_V2.prepare_selection(placed, 21) == ROULETTE_V2.prepare_selection(reordered, 21)
    assert [bet['type'] for bet in ROULETTE_V2.prepare_selection(placed, 21)['bets']] == [
        'red',
        'black',
        'dozen',
        'column',
        'number',
        'number',
    ]


@pytest.mark.parametrize(
    'selection',
    [
        None,
        [],
        {},
        {'bets': []},
        {'bets': {}},
        {'bets': [None]},
        {'bets': [{'type': 'red'}]},
        {'bets': [{'type': 'red', 'amount': 0}]},
        {'bets': [{'type': 'red', 'amount': -5}]},
        {'bets': [{'type': 'red', 'amount': True}]},
        {'bets': [{'type': 'red', 'amount': 5.0}]},
        {'bets': [{'type': 'red', 'amount': '5'}]},
        {'bets': [{'type': 'split', 'amount': 5}]},
        {'bets': [{'type': 'number', 'value': 37, 'amount': 5}]},
        {'bets': [{'type': 'red', 'value': 1, 'amount': 5}]},
        {'bets': [{'type': 'red', 'amount': 5, 'extra': 1}]},
        {'bets': [{'type': 'red', 'amount': 2}, {'type': 'red', 'amount': 3}]},
        {'bets': [{'type': 'number', 'value': 7, 'amount': 2}, {'type': 'number', 'value': 7, 'amount': 3}]},
        {'bets': [{'type': 'red', 'amount': 5}], 'type': 'red'},
        {'type': 'red', 'value': 1},
        {'type': 'number', 'value': 37},
    ],
)
def test_version_two_rejects_invalid_tables(selection):
    with pytest.raises(ValueError):
        ROULETTE_V2.prepare_selection(selection, 5)


@pytest.mark.parametrize('amount', [4, 6])
def test_the_bets_must_add_up_to_the_wager(amount):
    with pytest.raises(ValueError, match='add up'):
        ROULETTE_V2.prepare_selection(table(('red', 2), ('black', 3)), amount)


def test_version_two_fairness_receipt_replays_unchanged():
    random = FairRandom(
        server_seed='01' * 32,
        client_seed='characterization',
        commitment_id='00000000-0000-0000-0000-000000000001',
        game='roulette',
        rules_version=2,
    )
    selection = ROULETTE_V2.prepare_selection(table(('red', 5), ('number', 1, 22), ('dozen', 2, 2)), 8)
    # The rules version is part of the draw, so version 2 lands on its own number (14) for seeds that gave 12.
    assert ROULETTE_V2.outcome(random, selection) == {'number': 14, 'color': 'red', 'payout': 5 * 2 + 2 * 3}


def test_version_two_catalog_and_installed_math():
    ROULETTE_V2.verify()
    catalog = ROULETTE_V2.catalog_data(lambda multiplier: 1000 // (multiplier - 1))
    assert catalog['multiple_bets'] is True
    assert catalog['bet_types'] == ROULETTE_V1.catalog_data(lambda multiplier: 1000 // (multiplier - 1))['bet_types']
