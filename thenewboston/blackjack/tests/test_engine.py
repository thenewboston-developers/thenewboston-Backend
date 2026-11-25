from collections import Counter
from uuid import UUID

import pytest

from thenewboston.blackjack import engine
from thenewboston.blackjack.rules import BLACKJACK_V1
from thenewboston.casino.fairness import FairRandom


def deck(*cards):
    return [*cards, *(['2C'] * 40)]


@pytest.mark.parametrize(
    'cards,expected',
    [(['AS', 'AD'], 12), (['AS', 'AD', '9H'], 21), (['AS', 'AD', 'KH'], 12), (['KS', 'QD', '2H'], 22)],
)
def test_ace_totals(cards, expected):
    assert engine.total(cards) == expected


@pytest.mark.parametrize(
    'cards,outcome,multiplier',
    [
        (['AS', '9C', 'KH', '8D'], 'blackjack', 2.5),
        (['AS', 'AC', 'KH', 'KD'], 'push', 1),
        (['9S', 'AC', 'KH', 'KD'], 'loss', 0),
    ],
)
def test_naturals_settle_before_any_action(cards, outcome, multiplier):
    state = engine.initial_state(deck(*cards))
    assert (state['phase'], state['outcome'], state['multiplier']) == ('settled', outcome, multiplier)
    assert engine.available_actions(state) == []
    with pytest.raises(ValueError):
        engine.apply_action(state, deck(*cards), 'hit')


def test_dealer_stands_on_soft_seventeen():
    cards = deck('10C', 'AS', '8H', '6D', 'KC')
    state = engine.replay(cards, ['stand'])
    assert state['dealer_cards'] == ['AS', '6D']
    assert state['dealer_total'] == 17
    assert state['outcome'] == 'win'


def test_hit_to_twenty_one_completes_and_bust_does_not_draw_dealer_cards():
    cards = deck('5C', '6S', '6H', '9D', '10C', '4D')
    state = engine.replay(cards, ['hit'])
    assert state['player_total'] == 21 and state['dealer_total'] == 19
    assert state['phase'] == 'settled' and state['outcome'] == 'win'
    cards = deck('10C', '6S', '6H', '9D', '10D', '4D')
    state = engine.replay(cards, ['hit'])
    assert state['outcome'] == 'loss'
    assert state['dealer_cards'] == ['6S', '9D']


@pytest.mark.parametrize('action', ['split', 'insurance', 'surrender', None, 1, ['hit']])
def test_invalid_actions_are_rejected(action):
    cards = deck('5C', '10S', '6H', '7D')
    with pytest.raises(ValueError):
        engine.replay(cards, [action])


def test_double_only_first_decision_and_one_card():
    cards = deck('2C', '10S', '3H', '7D', '2D', '9D')
    state = engine.replay(cards, ['hit'])
    assert engine.available_actions(state) == ['hit', 'stand']
    with pytest.raises(ValueError):
        engine.replay(cards, ['hit', 'double'])
    state = engine.replay(cards, ['double'])
    assert state['player_cards'] == ['2C', '3H', '2D']
    assert state['phase'] == 'settled'
    assert state['doubled']


def test_fisher_yates_preserves_six_decks_and_uses_descending_bounds():
    class NoSwaps:
        bounds = []

        def below(self, bound):
            self.bounds.append(bound)
            return bound - 1

    random = NoSwaps()
    cards = engine.shuffled_deck(random)
    assert random.bounds == list(range(312, 1, -1))
    assert cards[:14] == [rank + 'C' for rank in engine.RANKS] + ['AD']
    assert len(cards) == 312 and set(Counter(cards).values()) == {6}


@pytest.mark.parametrize(
    'client,actions,player,dealer,outcome,multiplier',
    [
        ('vector-29', [], ['AD', 'JC'], ['6H', '10S'], 'blackjack', 2.5),
        ('vector-1', ['double'], ['6D', '2S', 'JS'], ['3H', '8H', '4S', '2C'], 'win', 4),
        ('vector-67', ['stand'], ['KH', '8C'], ['6H', 'AH'], 'win', 2),
    ],
)
def test_published_vectors_match_browser_verifier(client, actions, player, dealer, outcome, multiplier):
    random = FairRandom(
        server_seed='00' * 32,
        client_seed=client,
        commitment_id=UUID('00000000-0000-0000-0000-000000000001'),
        game='blackjack',
        rules_version=1,
    )
    state = engine.replay(engine.shuffled_deck(random), actions)
    assert state['player_cards'] == player
    assert state['dealer_cards'] == dealer
    assert state['outcome'] == outcome
    assert state['multiplier'] == multiplier
    assert state['revision'] == len(actions)
    BLACKJACK_V1.verify()
