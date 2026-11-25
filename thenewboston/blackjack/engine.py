"""Immutable six-deck Blackjack v1. No database or money mutations occur in this module."""

from copy import deepcopy

RANKS = ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')
SUITS = ('C', 'D', 'H', 'S')
DECKS = 6
TIMEOUT_SECONDS = 15 * 60


def total(cards):
    value, aces = 0, 0
    for card in cards:
        rank = card[:-1]
        if rank == 'A':
            value += 11
            aces += 1
        else:
            value += 10 if rank in ('J', 'Q', 'K') else int(rank)
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value


def shuffled_deck(random):
    deck = [rank + suit for _ in range(DECKS) for suit in SUITS for rank in RANKS]
    for index in range(len(deck) - 1, 0, -1):
        other = random.below(index + 1)
        deck[index], deck[other] = deck[other], deck[index]
    return deck


def finish(state, outcome):
    state['phase'] = 'settled'
    state['outcome'] = outcome
    stake_multiplier = 2 if state['doubled'] else 1
    state['multiplier'] = {'blackjack': 2.5, 'win': 2 * stake_multiplier, 'push': stake_multiplier, 'loss': 0}[outcome]


def initial_state(deck):
    state = {
        'player_cards': [deck[0], deck[2]],
        'dealer_cards': [deck[1], deck[3]],
        'cursor': 4,
        'doubled': False,
        'phase': 'player_turn',
        'outcome': None,
        'actions': [],
        'revision': 0,
        'multiplier': 0,
    }
    state['player_total'] = total(state['player_cards'])
    state['dealer_total'] = total(state['dealer_cards'])
    player_natural, dealer_natural = state['player_total'] == 21, state['dealer_total'] == 21
    if player_natural or dealer_natural:
        finish(state, 'push' if player_natural and dealer_natural else 'blackjack' if player_natural else 'loss')
    return state


def available_actions(state):
    if state['phase'] == 'settled':
        return []
    return ['hit', 'stand', 'double'] if state['revision'] == 0 else ['hit', 'stand']


def _draw(state, deck, who):
    state[f'{who}_cards'].append(deck[state['cursor']])
    state['cursor'] += 1
    state[f'{who}_total'] = total(state[f'{who}_cards'])


def _dealer_turn(state, deck):
    while state['dealer_total'] < 17:
        _draw(state, deck, 'dealer')
    player, dealer = state['player_total'], state['dealer_total']
    finish(state, 'win' if dealer > 21 or player > dealer else 'push' if player == dealer else 'loss')


def apply_action(state, deck, action):
    if action not in available_actions(state):
        raise ValueError('That action is not available for this hand.')
    state = deepcopy(state)
    state['actions'].append(action)
    state['revision'] += 1
    if action == 'stand':
        _dealer_turn(state, deck)
    else:
        state['doubled'] = action == 'double'
        _draw(state, deck, 'player')
        if state['player_total'] > 21:
            finish(state, 'loss')
        elif action == 'double' or state['player_total'] == 21:
            _dealer_turn(state, deck)
    return state


def replay(deck, actions):
    if not isinstance(actions, list) or len(actions) > 21:
        raise ValueError('Invalid Blackjack action transcript.')
    state = initial_state(deck)
    for action in actions:
        if not isinstance(action, str):
            raise ValueError('Invalid Blackjack action transcript.')
        state = apply_action(state, deck, action)
    return state
