import hashlib
import json

import pytest

from thenewboston.casino.fairness import FairRandom
from thenewboston.roulette.rules import ROULETTE_V1

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
