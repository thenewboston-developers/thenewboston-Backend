from collections import Counter
from dataclasses import replace
from math import comb

import pytest

from thenewboston.casino.fairness import FairRandom
from thenewboston.plinko.rules import PLINKO_V1


class FixedRandom:
    def __init__(self, draw):
        self.draw = draw
        self.calls = []

    def below(self, bound):
        self.calls.append(bound)
        assert 0 <= self.draw < bound
        return self.draw


def test_all_4096_paths_have_binomial_probabilities_and_exact_payouts():
    counts = Counter()
    returns = 0
    payouts = [50, 18, 8, 3, 1, 0, 0, 0, 1, 3, 8, 18, 50]
    for draw in range(4096):
        random = FixedRandom(draw)
        outcome = PLINKO_V1.outcome(random, {})
        assert random.calls == [4096]
        assert outcome['draw'] == draw
        assert outcome['path'] == [int(bit) for bit in f'{draw:012b}']
        assert outcome['slot'] == draw.bit_count()
        assert outcome['multiplier'] == payouts[outcome['slot']]
        counts[outcome['slot']] += 1
        returns += outcome['multiplier']
    assert counts == {slot: comb(12, slot) for slot in range(13)}
    assert returns == 3898
    assert 1 - PLINKO_V1.house_edge == returns / 4096


@pytest.mark.parametrize('selection', [None, {}])
def test_plinko_accepts_only_an_empty_selection(selection):
    assert PLINKO_V1.normalize_selection(selection) == {}
    assert PLINKO_V1.multiplier({}) == 50


@pytest.mark.parametrize('selection', [[], '', 0, False, True, {'risk': 'low'}, {'rows': 12}, {'slot': 0}])
def test_plinko_rejects_selection_overrides(selection):
    with pytest.raises(ValueError, match='does not accept a selection'):
        PLINKO_V1.normalize_selection(selection)


def test_fairness_vector_is_stable_and_reproducible_in_the_browser():
    random = FairRandom(
        server_seed='00' * 32,
        client_seed='test-client',
        commitment_id='00000000-0000-0000-0000-000000000001',
        game='plinko',
        rules_version=1,
    )
    assert PLINKO_V1.outcome(random, {}) == {
        'draw': 366,
        'path': [0, 0, 0, 1, 0, 1, 1, 0, 1, 1, 1, 0],
        'slot': 6,
        'multiplier': 0,
    }
    assert random.counter == 1


def test_catalog_publishes_every_pocket_and_installed_math_verifies():
    catalog = PLINKO_V1.catalog_data(lambda multiplier: 20)
    assert catalog['rows'] == 12
    assert len(catalog['payout_table']) == 13
    assert [pocket['slot'] for pocket in catalog['payout_table']] == list(range(13))
    assert sum(pocket['probability'] for pocket in catalog['payout_table']) == 1
    assert sum(pocket['multiplier'] * pocket['probability'] for pocket in catalog['payout_table']) == 3898 / 4096
    assert catalog['payout_table'][0] == {'slot': 0, 'multiplier': 50, 'probability': 1 / 4096}
    PLINKO_V1.verify()
    with pytest.raises(ValueError, match='house edge'):
        replace(PLINKO_V1, house_edge=0.01).verify()
    with pytest.raises(ValueError, match='50x'):
        replace(PLINKO_V1, max_multiplier=49).verify()
