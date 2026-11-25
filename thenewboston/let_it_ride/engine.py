"""Let It Ride version 1: the deck, the deal, hand ranking and the state of a hand. No database and no money here."""

from collections import Counter

RANKS = '23456789TJQKA'
SUITS = 'CDHS'
# Deal order of a fresh deck: 2C, 2D, 2H, 2S, 3C ... AS.
DECK = tuple(rank + suit for rank in RANKS for suit in SUITS)
BETS = 3
TIMEOUT_SECONDS = 600
# (hand, odds). A bet still riding is paid these odds to one and is returned as well; other hands lose it.
PAYTABLE = (
    ('royal_flush', 100),
    ('straight_flush', 50),
    ('four_of_a_kind', 25),
    ('full_house', 15),
    ('flush', 10),
    ('straight', 6),
    ('three_of_a_kind', 3),
    ('two_pair', 2),
    ('tens_or_better', 1),
)
ODDS = dict(PAYTABLE)
MAX_ODDS = max(ODDS.values())
NO_WIN = 'no_win'
ACTIONS = ('ride', 'pull')
# Lowest rank of a pair that pays: tens.
PAYING_PAIR = RANKS.index('T')
WHEEL = [0, 1, 2, 3, 12]


def deal(random):
    """Five draws without replacement from a fresh deck: three player cards, then the two community cards."""
    deck = list(DECK)
    cards = [deck.pop(random.below(len(deck))) for _ in range(5)]
    return cards[:3], cards[3:]


def _groups(cards):
    """Rank counts, largest group first; a tie goes to the higher rank."""
    counts = Counter(RANKS.index(card[0]) for card in cards)
    return sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)


def rank_hand(cards):
    """The paying hand made by five cards, or NO_WIN."""
    if len(cards) != 5 or len(set(cards)) != 5 or not set(cards) <= set(DECK):
        raise ValueError('A hand is five different cards.')
    groups = _groups(cards)
    shape = [count for _, count in groups]
    ranks = sorted(rank for rank, _ in groups)
    flush = len({card[1] for card in cards}) == 1
    straight = len(ranks) == 5 and (ranks[4] - ranks[0] == 4 or ranks == WHEEL)
    if straight and flush:
        return 'royal_flush' if ranks[0] == PAYING_PAIR else 'straight_flush'
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
    if shape == [2, 1, 1, 1] and groups[0][0] >= PAYING_PAIR:
        return 'tens_or_better'
    return NO_WIN


def already_pays(cards):
    """Whether these three or four cards already hold a paying hand, which no later card can take away."""
    groups = _groups(cards)
    shape = [count for _, count in groups]
    return shape[0] >= 3 or shape[:2] == [2, 2] or (shape[0] == 2 and groups[0][0] >= PAYING_PAIR)


def initial_state(cards, community):
    return {
        'cards': list(cards),
        'community': list(community),
        'decisions': [],
        'action_ids': [],
        'revision': 0,
        'phase': 'first',
        'riding': BETS,
        'hand': None,
        'odds': None,
    }


def visible_cards(state):
    """The cards the player has seen: a community card is turned after each decision."""
    return state['cards'] + state['community'][: len(state['decisions'])]


def apply_action(state, action, action_id=None):
    """The state after deciding the next bet. The second decision turns the last card and finishes the hand."""
    if state['phase'] == 'settled' or action not in ACTIONS:
        raise ValueError('That action is not available for this hand.')
    decisions = [*state['decisions'], action]
    finished = len(decisions) == BETS - 1
    hand = rank_hand(state['cards'] + state['community']) if finished else None
    return {
        **state,
        'decisions': decisions,
        'action_ids': [*state['action_ids'], action_id],
        'revision': len(decisions),
        'phase': 'settled' if finished else 'second',
        'riding': BETS - decisions.count('pull'),
        'hand': hand,
        'odds': ODDS.get(hand, 0) if finished else None,
    }


def replay(cards, community, decisions, action_ids):
    """Rebuild a hand from its deal and its recorded decisions."""
    if len(decisions) != len(action_ids) or len(decisions) > BETS - 1:
        raise ValueError('A hand has at most two decisions, each with its action.')
    state = initial_state(cards, community)
    for action, action_id in zip(decisions, action_ids):
        state = apply_action(state, action, action_id)
    return state


def timeout_action(state):
    """An unattended bet rides only when the hand already pays, so it cannot lose; otherwise it is pulled back."""
    return 'ride' if already_pays(visible_cards(state)) else 'pull'


def payout(amount, state):
    """Total returned for a finished hand: every pulled bet, plus each riding bet with its winnings."""
    if state['phase'] != 'settled' or amount % BETS:
        raise ValueError('Only a finished hand of three equal bets has a payout.')
    bet = amount // BETS
    riding = state['riding']
    return bet * (BETS - riding) + (bet * riding * (state['odds'] + 1) if state['odds'] else 0)
