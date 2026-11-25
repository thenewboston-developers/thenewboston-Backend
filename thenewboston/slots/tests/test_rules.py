import hashlib
import json
from collections import Counter

import pytest

from thenewboston.casino.fairness import FairRandom
from thenewboston.slots.rules import SLOTS_V1


class FixedRandom:
    def __init__(self, value):
        self.value = value

    def below(self, bound):
        assert bound == 10000
        return self.value


def test_all_version_one_outcomes_are_identical_to_the_original_casino_implementation():
    outcomes = [SLOTS_V1.outcome(FixedRandom(draw), {}) for draw in range(10000)]
    # Captured from the deployed v1 implementation before extracting the game app.
    fingerprint = hashlib.sha256(json.dumps(outcomes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert fingerprint == '195749db636db05259be1ad30302bdf7b29a6abb918050005b8f1d6e1b458b9f'
    counts = Counter(result['multiplier'] for result in outcomes)
    assert counts == {0: 5885, 1: 1600, 2: 2000, 5: 400, 10: 100, 50: 10, 100: 5}
    assert sum(multiplier * count for multiplier, count in counts.items()) == 9600
    assert max(counts) == 100


def test_version_one_fairness_receipt_replays_unchanged():
    random = FairRandom(
        server_seed='01' * 32,
        client_seed='characterization',
        commitment_id='00000000-0000-0000-0000-000000000001',
        game='slots',
        rules_version=1,
    )
    assert SLOTS_V1.outcome(random, {}) == {'draw': 8981, 'multiplier': 2, 'symbols': ['lemon', 'lemon', 'lemon']}


@pytest.mark.parametrize('selection', [None, {}])
def test_slots_has_no_selection(selection):
    assert SLOTS_V1.normalize_selection(selection) == {}
    assert SLOTS_V1.multiplier({}) == 100


@pytest.mark.parametrize('selection', [[], {'type': 'red'}, 'slots', 1, False])
def test_slots_rejects_selections(selection):
    with pytest.raises(ValueError, match='Slots does not accept a selection.'):
        SLOTS_V1.normalize_selection(selection)


def test_slots_catalog_and_installed_math():
    SLOTS_V1.verify()
    assert SLOTS_V1.catalog_multiplier == 100
    assert SLOTS_V1.catalog_data(lambda multiplier: 1000 // (multiplier - 1)) == {
        'payout_table': [
            {'multiplier': 0, 'probability': 0.5885},
            {'multiplier': 1, 'probability': 0.16},
            {'multiplier': 2, 'probability': 0.2},
            {'multiplier': 5, 'probability': 0.04},
            {'multiplier': 10, 'probability': 0.01},
            {'multiplier': 50, 'probability': 0.001},
            {'multiplier': 100, 'probability': 0.0005},
        ]
    }
