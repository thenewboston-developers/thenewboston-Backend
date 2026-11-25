"""Immutable Jacks or Better Video Poker v1. No database or money mutations occur in this module."""

from collections import Counter
from copy import deepcopy
from itertools import combinations_with_replacement
from math import comb, prod

RANKS = ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')
SUITS = ('C', 'D', 'H', 'S')
HAND_SIZE = 5
TIMEOUT_SECONDS = 15 * 60
# Total-return multipliers, stake included: the classic "9/6" table with a flat 250-for-1 royal flush.
PAY_TABLE = (
    ('royal_flush', 'Royal Flush', 250),
    ('straight_flush', 'Straight Flush', 50),
    ('four_of_a_kind', 'Four of a Kind', 25),
    ('full_house', 'Full House', 9),
    ('flush', 'Flush', 6),
    ('straight', 'Straight', 4),
    ('three_of_a_kind', 'Three of a Kind', 3),
    ('two_pair', 'Two Pair', 2),
    ('jacks_or_better', 'Jacks or Better', 1),
)
MULTIPLIERS = {**{hand: multiplier for hand, _, multiplier in PAY_TABLE}, 'nothing': 0}
MAX_MULTIPLIER = 250
# Rank indexes follow RANKS: a pair of jacks, queens, kings or aces returns the stake.
HIGH_PAIR_RANKS = frozenset({0, 10, 11, 12})
ROYAL_RANKS = [0, 9, 10, 11, 12]
STAND_PAT = 'draw:11111'
# How many of the 2,598,960 five-card hands fall in each category; `verify` recounts them.
HAND_COUNTS = {
    'royal_flush': 4,
    'straight_flush': 36,
    'four_of_a_kind': 624,
    'full_house': 3744,
    'flush': 5108,
    'straight': 10200,
    'three_of_a_kind': 54912,
    'two_pair': 123552,
    'jacks_or_better': 337920,
    'nothing': 2062860,
}
# Return of the strategy that maximizes every hand's expected payout, from enumerating every deal and every hold.
OPTIMAL_RETURN = (35523565111, 36110924850)


def classify(ranks, flush):
    """Category of five sorted rank indexes (0 is the ace) that do or do not share one suit."""
    counts = sorted(Counter(ranks).values(), reverse=True)
    # An ace plays low in A-2-3-4-5 and high in 10-J-Q-K-A. A straight never wraps around the ace.
    royal = ranks == ROYAL_RANKS
    straight = counts[0] == 1 and (ranks[4] - ranks[0] == 4 or royal)
    if straight and flush:
        return 'royal_flush' if royal else 'straight_flush'
    if counts[0] == 4:
        return 'four_of_a_kind'
    if counts == [3, 2]:
        return 'full_house'
    if flush:
        return 'flush'
    if straight:
        return 'straight'
    if counts[0] == 3:
        return 'three_of_a_kind'
    if counts == [2, 2, 1]:
        return 'two_pair'
    if counts[0] == 2 and next(rank for rank in ranks if ranks.count(rank) == 2) in HIGH_PAIR_RANKS:
        return 'jacks_or_better'
    return 'nothing'


def evaluate(cards):
    if len(cards) != HAND_SIZE or len(set(cards)) != HAND_SIZE:
        raise ValueError('A Video Poker hand has five different cards.')
    ranks = sorted(RANKS.index(card[:-1]) for card in cards)
    return classify(ranks, len({card[-1] for card in cards}) == 1)


def hand_counts():
    """Exact category frequencies over all C(52, 5) hands, grouped by rank pattern instead of dealing each one."""
    counts = dict.fromkeys(MULTIPLIERS, 0)
    for ranks in combinations_with_replacement(range(len(RANKS)), HAND_SIZE):
        multiplicities = Counter(ranks).values()
        if max(multiplicities) > len(SUITS):
            continue
        ranks = list(ranks)
        if len(multiplicities) == HAND_SIZE:
            # Five different ranks: four of the 4^5 suit assignments are flushes.
            counts[classify(ranks, True)] += len(SUITS)
            counts[classify(ranks, False)] += len(SUITS) ** HAND_SIZE - len(SUITS)
        else:
            counts[classify(ranks, False)] += prod(comb(len(SUITS), multiplicity) for multiplicity in multiplicities)
    return counts


def shuffled_deck(random):
    deck = [rank + suit for suit in SUITS for rank in RANKS]
    for index in range(len(deck) - 1, 0, -1):
        other = random.below(index + 1)
        deck[index], deck[other] = deck[other], deck[index]
    return deck


def initial_state(deck):
    hand = list(deck[:HAND_SIZE])
    return {
        'dealt': hand,
        'hand': list(hand),
        'held': None,
        'phase': 'draw',
        'category': evaluate(hand),
        'multiplier': 0,
        'actions': [],
        'revision': 0,
    }


def available_actions(state):
    return ['draw'] if state['phase'] == 'draw' else []


def parse_action(action):
    """`draw:10110` holds the first, third and fourth cards and replaces the other two."""
    if (
        not isinstance(action, str)
        or len(action) != len(STAND_PAT)
        or not action.startswith('draw:')
        or set(action[5:]) - {'0', '1'}
    ):
        raise ValueError('Choose which cards to hold, then draw.')
    return [flag == '1' for flag in action[5:]]


def apply_action(state, deck, action):
    held = parse_action(action)
    if state['phase'] != 'draw':
        raise ValueError('That action is not available for this hand.')
    state = deepcopy(state)
    # Replacements come off the top of the remaining deck, filling discarded positions from left to right.
    replacements = iter(deck[HAND_SIZE : 2 * HAND_SIZE])
    state['hand'] = [card if keep else next(replacements) for card, keep in zip(state['dealt'], held, strict=True)]
    state['held'] = held
    state['actions'].append(action)
    state['revision'] += 1
    state['phase'] = 'settled'
    state['category'] = evaluate(state['hand'])
    state['multiplier'] = MULTIPLIERS[state['category']]
    return state


def replay(deck, actions):
    if not isinstance(actions, list) or len(actions) > 1:
        raise ValueError('Invalid Video Poker action transcript.')
    state = initial_state(deck)
    for action in actions:
        state = apply_action(state, deck, action)
    return state
