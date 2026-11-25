import random
from collections import Counter
from fractions import Fraction
from itertools import combinations

import pytest

from thenewboston.casino.fairness import FairRandom
from thenewboston.video_poker import engine
from thenewboston.video_poker.rules import OPTIMAL_RETURN, VIDEO_POKER_V1

DECK = [rank + suit for suit in engine.SUITS for rank in engine.RANKS]
ZERO_SEED = '00' * 32
COMMITMENT = '00000000-0000-0000-0000-000000000001'


def fair_deck(client_seed):
    source = FairRandom(
        server_seed=ZERO_SEED, client_seed=client_seed, commitment_id=COMMITMENT, game='video_poker', rules_version=1
    )
    return engine.shuffled_deck(source), source


def reference_category(cards):
    """Deliberately different from the engine: ranks as 2..14, straights listed one by one."""
    values = sorted({'A': 14, 'K': 13, 'Q': 12, 'J': 11}.get(card[:-1]) or int(card[:-1]) for card in cards)
    groups = sorted(Counter(values).items(), key=lambda item: (-item[1], -item[0]))
    flush = all(card[-1] == cards[0][-1] for card in cards)
    straights = [list(range(low, low + 5)) for low in range(2, 11)] + [[2, 3, 4, 5, 14]]
    straight = values in straights
    if straight and flush:
        return 'royal_flush' if values == [10, 11, 12, 13, 14] else 'straight_flush'
    shape = [count for _, count in groups]
    if shape == [4, 1]:
        return 'four_of_a_kind'
    if shape == [3, 2]:
        return 'full_house'
    if flush:
        return 'flush'
    if straight:
        return 'straight'
    if shape == [3, 1, 1]:
        return 'three_of_a_kind'
    if shape == [2, 2, 1]:
        return 'two_pair'
    if shape == [2, 1, 1, 1] and groups[0][0] >= 11:
        return 'jacks_or_better'
    return 'nothing'


@pytest.mark.parametrize(
    'cards,category',
    [
        (['10S', 'JS', 'QS', 'KS', 'AS'], 'royal_flush'),
        (['AH', 'KH', 'QH', 'JH', '10H'], 'royal_flush'),
        (['9S', '10S', 'JS', 'QS', 'KS'], 'straight_flush'),
        (['AD', '2D', '3D', '4D', '5D'], 'straight_flush'),
        (['7C', '7D', '7H', '7S', 'AC'], 'four_of_a_kind'),
        (['KC', 'KD', 'KH', '2S', '2C'], 'full_house'),
        (['2C', '2D', 'KH', 'KS', 'KC'], 'full_house'),
        (['AD', '3D', '8D', 'JD', 'QD'], 'flush'),
        (['JC', 'QC', 'KC', 'AC', '2C'], 'flush'),
        (['AC', '2D', '3H', '4S', '5C'], 'straight'),
        (['10C', 'JD', 'QH', 'KS', 'AC'], 'straight'),
        (['5C', '6D', '7H', '8S', '9C'], 'straight'),
        (['QC', 'KD', 'AH', '2S', '3C'], 'nothing'),
        (['KC', 'AD', '2H', '3S', '4C'], 'nothing'),
        (['4C', '4D', '4H', '9S', 'KC'], 'three_of_a_kind'),
        (['4C', '4D', '9H', '9S', 'KC'], 'two_pair'),
        (['2C', '2D', '3H', '3S', 'KC'], 'two_pair'),
        (['JC', 'JD', '3H', '8S', 'KC'], 'jacks_or_better'),
        (['QC', 'QD', '3H', '8S', '2C'], 'jacks_or_better'),
        (['KC', 'KD', '3H', '8S', '2C'], 'jacks_or_better'),
        (['AC', 'AD', '3H', '8S', '2C'], 'jacks_or_better'),
        (['10C', '10D', '3H', '8S', 'AC'], 'nothing'),
        (['2C', '2D', '3H', '8S', 'AC'], 'nothing'),
        (['2C', '5D', '9H', 'JS', 'AC'], 'nothing'),
    ],
)
def test_hand_categories(cards, category):
    assert engine.evaluate(cards) == category
    assert engine.evaluate(cards[::-1]) == category


def test_every_five_card_hand_is_counted_in_exactly_one_category():
    counts = engine.hand_counts()
    assert counts == engine.HAND_COUNTS
    assert sum(counts.values()) == 2598960
    # Dealt hands alone return a third of the wager; the rest of the return comes from drawing.
    assert Fraction(sum(engine.MULTIPLIERS[hand] * count for hand, count in counts.items()), 2598960) == Fraction(
        873304, 2598960
    )


def test_evaluator_matches_an_independent_reference_on_dealt_and_structured_hands():
    source = random.Random(20261125)
    hands = [source.sample(DECK, 5) for _ in range(4000)]
    # Every hand of the spade suit and of the two red aces-to-fives exercises flushes and straights densely.
    hands += [list(hand) for hand in combinations(DECK[39:], 5)]
    hands += [list(hand) for hand in combinations(DECK[13:18] + DECK[26:31], 5)]
    # Aces, jacks and queens of every suit are dense in pairs, trips, full houses and four of a kind.
    hands += [list(hand) for hand in combinations([card for card in DECK if card[:-1] in ('A', 'J', 'Q')], 5)]
    assert all(engine.evaluate(hand) == reference_category(hand) for hand in hands)
    assert {engine.evaluate(hand) for hand in hands} == set(engine.MULTIPLIERS)


@pytest.mark.parametrize('cards', [['AS'] * 5, ['AS', 'KS', 'QS', 'JS'], ['AS', 'KS', 'QS', 'JS', '10S', '9S']])
def test_malformed_hands_are_rejected(cards):
    with pytest.raises(ValueError):
        engine.evaluate(cards)


def test_shuffle_is_a_reproducible_permutation_of_one_deck():
    deck, source = fair_deck('vector-1')
    assert sorted(deck) == sorted(DECK) and len(set(deck)) == 52
    assert source.counter >= 51
    assert deck == fair_deck('vector-1')[0]
    assert deck != fair_deck('vector-2')[0]


def test_public_reference_vectors():
    deck, _ = fair_deck('vector-1')
    assert deck[:10] == ['3D', '2S', '9D', '3S', 'QC', '9S', 'QD', '10S', 'KH', '2H']
    state = engine.replay(deck, ['draw:10110'])
    assert state['hand'] == ['3D', '9S', '9D', '3S', 'QD']
    assert (state['category'], state['multiplier']) == ('two_pair', 2)
    deck, _ = fair_deck('test-client')
    assert deck[:10] == ['8D', '9H', '6H', 'AD', '10S', '3D', 'JD', 'QD', '8S', '4D']
    state = engine.replay(deck, ['draw:10010'])
    assert state['hand'] == ['8D', '3D', 'JD', 'AD', 'QD']
    assert (state['category'], state['multiplier']) == ('flush', 6)


def test_deal_waits_for_one_draw_and_replacements_fill_discards_from_the_left():
    deck = ['KS', 'KH', '4D', '7C', 'KD', '2S', '2H', 'AC', 'AD', 'AH', '9C']
    state = engine.initial_state(deck)
    assert state == {
        'dealt': ['KS', 'KH', '4D', '7C', 'KD'],
        'hand': ['KS', 'KH', '4D', '7C', 'KD'],
        'held': None,
        'phase': 'draw',
        'category': 'three_of_a_kind',
        'multiplier': 0,
        'actions': [],
        'revision': 0,
    }
    assert engine.available_actions(state) == ['draw']
    drawn = engine.apply_action(state, deck, 'draw:11001')
    assert drawn['hand'] == ['KS', 'KH', '2S', '2H', 'KD']
    assert drawn['held'] == [True, True, False, False, True]
    assert (drawn['category'], drawn['multiplier'], drawn['phase']) == ('full_house', 9, 'settled')
    assert (drawn['actions'], drawn['revision']) == (['draw:11001'], 1)
    assert engine.available_actions(drawn) == []
    assert state['hand'] == state['dealt'] and state['actions'] == []
    assert engine.apply_action(state, deck, 'draw:11111')['hand'] == state['dealt']
    assert engine.apply_action(state, deck, 'draw:00000')['hand'] == ['2S', '2H', 'AC', 'AD', 'AH']
    assert engine.apply_action(state, deck, 'draw:00001')['hand'] == ['2S', '2H', 'AC', 'AD', 'KD']
    with pytest.raises(ValueError, match='not available'):
        engine.apply_action(drawn, deck, 'draw:11111')
    assert engine.replay(deck, ['draw:11001']) == drawn
    with pytest.raises(ValueError):
        engine.replay(deck, ['draw:11001', 'draw:11111'])


@pytest.mark.parametrize(
    'action', ['draw', 'draw:1111', 'draw:111111', 'draw:1101x', 'hold:11011', 'DRAW:11011', None, 11011, ['draw']]
)
def test_invalid_actions_are_rejected(action):
    deck = DECK[:10]
    with pytest.raises(ValueError):
        engine.apply_action(engine.initial_state(deck), deck, action)
    with pytest.raises(ValueError):
        engine.replay(deck, [action])


def test_rules_publish_the_classic_pay_table_and_cover_a_royal_flush():
    VIDEO_POKER_V1.verify()
    assert VIDEO_POKER_V1.settlement_mode == 'interactive'
    assert VIDEO_POKER_V1.multiplier({}) == VIDEO_POKER_V1.max_multiplier == 250
    assert VIDEO_POKER_V1.normalize_selection(None) == VIDEO_POKER_V1.normalize_selection({}) == {}
    with pytest.raises(ValueError):
        VIDEO_POKER_V1.normalize_selection({'hold': [0]})
    data = VIDEO_POKER_V1.catalog_data(lambda multiplier: 0)
    assert [(row['hand'], row['multiplier']) for row in data['pay_table']] == [
        ('royal_flush', 250),
        ('straight_flush', 50),
        ('four_of_a_kind', 25),
        ('full_house', 9),
        ('flush', 6),
        ('straight', 4),
        ('three_of_a_kind', 3),
        ('two_pair', 2),
        ('jacks_or_better', 1),
    ]
    assert data['optimal_return'] == OPTIMAL_RETURN == pytest.approx(0.98373457)
    assert Fraction(*engine.OPTIMAL_RETURN).as_integer_ratio() == engine.OPTIMAL_RETURN
    assert VIDEO_POKER_V1.house_edge == pytest.approx(0.01626543)


def test_verification_fails_when_the_evaluator_or_pay_table_changes(monkeypatch):
    monkeypatch.setitem(engine.HAND_COUNTS, 'flush', 5107)
    with pytest.raises(ValueError, match='hand evaluation'):
        VIDEO_POKER_V1.verify()
    monkeypatch.undo()
    monkeypatch.setattr(engine, 'PAY_TABLE', engine.PAY_TABLE[:-1])
    with pytest.raises(ValueError, match='pay table'):
        VIDEO_POKER_V1.verify()
