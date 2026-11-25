from collections import Counter
from fractions import Fraction
from itertools import combinations, combinations_with_replacement, permutations
from math import comb

import pytest

from thenewboston.let_it_ride import engine
from thenewboston.let_it_ride.rules import OPTIMAL_EDGE_PER_BET

RANKS = engine.RANKS
CARDS = [(rank, suit) for rank in range(13) for suit in range(4)]
HIGH = RANKS.index('T')


class Draws:
    def __init__(self, *values):
        self.values = list(values)
        self.bounds = []

    def below(self, bound):
        self.bounds.append(bound)
        return self.values.pop(0)


def rank_patterns():
    """Every five-card rank pattern with its hand when the suits differ and, where possible, when they match."""
    for ranks in combinations_with_replacement(range(13), 5):
        counts = Counter(ranks)
        if max(counts.values()) > 4:
            continue
        seen = Counter()
        offsuit = []
        for position, rank in enumerate(ranks):
            # Repeated ranks need different suits; five different ranks are spread over the suits so they never match.
            suit = seen[rank] if len(counts) < 5 else position % 4
            offsuit.append(RANKS[rank] + engine.SUITS[suit])
            seen[rank] += 1
        suited = engine.rank_hand([RANKS[rank] + 'S' for rank in ranks]) if len(counts) == 5 else None
        yield ranks, counts, engine.rank_hand(offsuit), suited


def test_the_deck_and_the_deal_order_are_fixed():
    assert len(engine.DECK) == len(set(engine.DECK)) == 52
    assert engine.DECK[:5] == ('2C', '2D', '2H', '2S', '3C')
    assert engine.DECK[-1] == 'AS'
    random = Draws(51, 0, 0, 0, 47)
    assert engine.deal(random) == (['AS', '2C', '2D'], ['2H', 'AH'])
    # Five draws without replacement: each bound is the number of cards left in the deck.
    assert random.bounds == [52, 51, 50, 49, 48]


def test_every_five_card_hand_is_ranked_into_the_standard_number_of_hands():
    hands = Counter()
    for _, counts, offsuit, suited in rank_patterns():
        ways = 1
        for count in counts.values():
            ways *= comb(4, count)
        if suited is None:
            hands[offsuit] += ways
        else:
            # Five different ranks: 4 of their 1,024 suit combinations are flushes.
            hands[suited] += 4
            hands[offsuit] += ways - 4
    assert hands == {
        'royal_flush': 4,
        'straight_flush': 36,
        'four_of_a_kind': 624,
        'full_house': 3744,
        'flush': 5108,
        'straight': 10200,
        'three_of_a_kind': 54912,
        'two_pair': 123552,
        'tens_or_better': 422400,
        engine.NO_WIN: 1978380,
    }
    assert sum(hands.values()) == comb(52, 5)


@pytest.mark.parametrize(
    'cards,hand',
    [
        (['AS', 'KS', 'QS', 'JS', 'TS'], 'royal_flush'),
        (['9H', 'KH', 'QH', 'JH', 'TH'], 'straight_flush'),
        (['5C', '4C', '3C', '2C', 'AC'], 'straight_flush'),
        (['5C', '4D', '3C', '2C', 'AC'], 'straight'),
        (['QC', 'KD', 'AC', '2C', '3C'], engine.NO_WIN),
        (['TC', 'TD', '4H', '4S', '4C'], 'full_house'),
        (['9C', '9D', 'AH', 'KS', 'QC'], engine.NO_WIN),
        (['TC', 'TD', 'AH', 'KS', 'QC'], 'tens_or_better'),
        (['AC', 'AD', '2H', '3S', '4C'], 'tens_or_better'),
        (['2C', '2D', '3H', '3S', '4C'], 'two_pair'),
    ],
)
def test_hand_ranking_edges(cards, hand):
    assert engine.rank_hand(cards) == hand


@pytest.mark.parametrize('cards', [['AS'] * 5, ['AS', 'KS', 'QS', 'JS'], ['AS', 'KS', 'QS', 'JS', '1S']])
def test_only_five_different_real_cards_are_a_hand(cards):
    with pytest.raises(ValueError):
        engine.rank_hand(cards)


@pytest.mark.parametrize(
    'cards,pays',
    [
        (['TC', 'TD', '2H'], True),
        (['9C', '9D', '2H'], False),
        (['2C', '2D', '2H'], True),
        (['2C', '2D', '3H', '3S'], True),
        (['2C', '2D', '3H', 'AS'], False),
        (['AC', 'KC', 'QC', 'JC'], False),
        (['AC', 'AD', '2H', '2S'], True),
    ],
)
def test_a_made_hand_is_recognised_before_the_last_card(cards, pays):
    assert engine.already_pays(cards) is pays


def test_a_made_hand_can_never_end_as_a_loss():
    for three in (['TC', 'TD', '2H'], ['7C', '7D', '7H'], ['AC', 'AD', 'KH']):
        rest = [card for card in engine.DECK if card not in three]
        assert all(engine.rank_hand([*three, *pair]) != engine.NO_WIN for pair in combinations(rest, 2))


def test_a_hand_takes_two_decisions_and_turns_one_card_after_each():
    state = engine.initial_state(['TC', 'TD', '2H'], ['3S', 'TH'])
    assert (state['phase'], state['revision'], state['riding']) == ('first', 0, 3)
    assert engine.visible_cards(state) == ['TC', 'TD', '2H']
    state = engine.apply_action(state, 'pull', 'first-action')
    assert (state['phase'], state['revision'], state['riding'], state['hand']) == ('second', 1, 2, None)
    assert engine.visible_cards(state) == ['TC', 'TD', '2H', '3S']
    state = engine.apply_action(state, 'ride', 'second-action')
    assert (state['phase'], state['revision'], state['riding']) == ('settled', 2, 2)
    assert (state['hand'], state['odds']) == ('three_of_a_kind', 3)
    assert state == engine.replay(['TC', 'TD', '2H'], ['3S', 'TH'], ['pull', 'ride'], ['first-action', 'second-action'])
    with pytest.raises(ValueError):
        engine.apply_action(state, 'ride')
    with pytest.raises(ValueError):
        engine.apply_action(engine.initial_state(['TC', 'TD', '2H'], ['3S', 'TH']), 'fold')
    with pytest.raises(ValueError):
        engine.replay(['TC', 'TD', '2H'], ['3S', 'TH'], ['pull', 'ride', 'ride'], [None, None, None])


@pytest.mark.parametrize(
    'decisions,community,paid',
    [
        # Three of a kind pays 3 to 1 on each bet left riding; a pulled bet simply comes back.
        (['ride', 'ride'], ['3S', 'TH'], 3 * 4 * 5),
        (['pull', 'ride'], ['3S', 'TH'], 5 + 2 * 4 * 5),
        (['pull', 'pull'], ['3S', 'TH'], 2 * 5 + 4 * 5),
        # A losing hand keeps only what was pulled back.
        (['ride', 'ride'], ['3S', '4H'], 3 * 2 * 5),
        (['pull', 'pull'], ['3S', '9H'], 2 * 5 + 2 * 5),
    ],
)
def test_payout_returns_pulled_bets_and_pays_riding_bets(decisions, community, paid):
    state = engine.replay(['TC', 'TD', '2H'], community, decisions, [None, None])
    assert engine.payout(15, state) == paid
    assert engine.payout(15, state) <= 15 * (engine.MAX_ODDS + 1)


def test_payout_needs_a_finished_hand_of_three_equal_bets():
    state = engine.initial_state(['TC', 'TD', '2H'], ['3S', 'TH'])
    with pytest.raises(ValueError):
        engine.payout(15, state)
    finished = engine.replay(['TC', 'TD', '2H'], ['3S', 'TH'], ['ride', 'ride'], [None, None])
    with pytest.raises(ValueError):
        engine.payout(16, finished)
    royal = engine.replay(['TS', 'JS', 'QS'], ['KS', 'AS'], ['ride', 'ride'], [None, None])
    assert engine.payout(3, royal) == 3 * 101


def test_an_unattended_bet_rides_only_when_it_cannot_lose():
    paying = engine.initial_state(['TC', 'TD', '2H'], ['3S', '4H'])
    assert engine.timeout_action(paying) == 'ride'
    drawing = engine.initial_state(['AS', 'KS', 'QS'], ['JS', '2H'])
    assert engine.timeout_action(drawing) == 'pull'
    # The first community card can make the hand: the second bet then rides.
    improved = engine.apply_action(engine.initial_state(['AS', 'KS', '2S'], ['AH', '3D']), 'pull')
    assert engine.timeout_action(improved) == 'ride'


def spread(ranks):
    """How far apart the lowest and highest cards are, with the ace high only."""
    return max(ranks) - min(ranks)


def published_first_decision(hand):
    """The strategy printed on the rules page for the first bet (three cards)."""
    ranks = sorted(rank for rank, _ in hand)
    high = sum(rank >= HIGH for rank in ranks)
    if engine.already_pays([RANKS[rank] + engine.SUITS[suit] for rank, suit in hand]):
        return True
    if len(set(ranks)) < 3:
        return False
    if len({suit for _, suit in hand}) == 1:
        gaps = spread(ranks) - 2
        return (gaps <= 1 and high >= 1) or (gaps == 2 and high >= 2)
    return ranks == [RANKS.index('T'), RANKS.index('J'), RANKS.index('Q')]


def published_second_decision(hand):
    """The strategy printed on the rules page for the second bet (four cards)."""
    ranks = sorted(rank for rank, _ in hand)
    if engine.already_pays([RANKS[rank] + engine.SUITS[suit] for rank, suit in hand]):
        return True
    if len({suit for _, suit in hand}) == 1:
        return True
    if len(set(ranks)) < 4:
        return False
    return ranks[0] >= HIGH or (spread(ranks) == 3 and ranks[3] < RANKS.index('A'))


def test_published_house_edge_and_strategy_are_exactly_the_best_play_over_every_deal():
    returns = {}
    for ranks, _, offsuit, suited in rank_patterns():
        returns[ranks] = (engine.ODDS.get(offsuit, -1) + 1, None if suited is None else engine.ODDS.get(suited, -1) + 1)
    # Three-card hands that differ only by which suit is which play identically: solve one of each.
    suit_maps = list(permutations(range(4)))
    classes = Counter()
    for hand in combinations(CARDS, 3):
        classes[min(tuple(sorted((rank, mapping[suit]) for rank, suit in hand)) for mapping in suit_maps)] += 1
    assert sum(classes.values()) == comb(52, 3)
    returned = 0
    for hand, weight in classes.items():
        rest = [card for card in CARDS if card not in hand]
        suited = len({suit for _, suit in hand}) == 1
        ranks = [rank for rank, _ in hand]
        by_fourth = dict.fromkeys(rest, 0)
        everything = 0
        for first, second in combinations(rest, 2):
            entry = returns[tuple(sorted((*ranks, first[0], second[0])))]
            value = entry[1] if suited and first[1] == second[1] == hand[0][1] else entry[0]
            by_fourth[first] += value
            by_fourth[second] += value
            everything += value
        # A bet is worth leaving out only when it returns more than itself on average.
        ride_first = everything > comb(49, 2)
        assert published_first_decision(hand) is ride_first, hand
        for fourth, total in by_fourth.items():
            ride_second = total > 48
            assert published_second_decision((*hand, fourth)) is ride_second, (hand, fourth)
            returned += weight * ((total if ride_first else 48) + (total if ride_second else 48) + total)
    deals = comb(52, 3) * 49 * 48
    edge = Fraction(3 * deals - returned, deals)
    assert edge == Fraction(7979, 249900)
    assert OPTIMAL_EDGE_PER_BET == 7979 / 249900
