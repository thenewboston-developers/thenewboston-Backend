import hashlib
import json
from collections import Counter

import pytest

from thenewboston.casino.fairness import FairRandom
from thenewboston.slots.rules import SLOT_LOSING_LINES, SLOT_SYMBOLS, SLOTS_V1, SLOTS_V2


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


def test_version_two_only_varies_the_symbols_of_losing_draws():
    lines = Counter()
    for draw in range(10000):
        old = SLOTS_V1.outcome(FixedRandom(draw), {})
        new = SLOTS_V2.outcome(FixedRandom(draw), {})
        assert (new['draw'], new['multiplier']) == (old['draw'], old['multiplier'])
        if new['multiplier']:
            assert new['symbols'] == old['symbols'] == SLOT_SYMBOLS[new['multiplier']]
        else:
            assert old['symbols'] == ['cherry', 'lemon', 'bar']
            # Three different symbols: a loss never shows a pair that looks like it almost won.
            assert len(set(new['symbols'])) == 3
            lines[tuple(new['symbols'])] += 1
    assert len(SLOT_LOSING_LINES) == len(lines) == 120
    assert set(lines.values()) == {49, 50}
    assert SLOT_LOSING_LINES[0] == ['cherry', 'lemon', 'bell']
    assert SLOT_LOSING_LINES[-1] == ['seven', 'diamond', 'bar']
    assert SLOTS_V1.outcome(FixedRandom(4999), {})['symbols'] == ['cherry', 'lemon', 'bar']


def test_version_two_fairness_vectors_match_the_browser_verifier():
    # The frontend verifier tests replay these exact receipts.
    def outcome(client_seed):
        random = FairRandom(
            server_seed='00' * 32,
            client_seed=client_seed,
            commitment_id='00000000-0000-0000-0000-000000000001',
            game='slots',
            rules_version=2,
        )
        return SLOTS_V2.outcome(random, {})

    assert outcome('test-client') == {'draw': 1640, 'multiplier': 0, 'symbols': ['diamond', 'cherry', 'lemon']}
    assert outcome('v2-b') == {'draw': 8368, 'multiplier': 2, 'symbols': ['lemon', 'lemon', 'lemon']}


def test_version_two_keeps_the_version_one_contract():
    SLOTS_V2.verify()
    assert (SLOTS_V2.version, SLOTS_V2.max_multiplier, SLOTS_V2.catalog_multiplier) == (2, 100, 100)
    assert SLOTS_V2.house_edge == SLOTS_V1.house_edge
    assert SLOTS_V2.catalog_data(lambda multiplier: 10) == SLOTS_V1.catalog_data(lambda multiplier: 10)
    assert SLOTS_V2.normalize_selection(None) == {}
