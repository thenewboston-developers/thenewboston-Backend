"""A bounded, local computer opponent for free practice games.

Easy plays any legal pit. Normal looks two moves ahead. Hard searches deeper,
but only until a fixed number of positions has been examined, so one decision
stays cheap on a small worker no matter how the board looks.
"""

from random import SystemRandom

from .rules import PITS, STORE, is_finished, legal_pits, opponent, pit_index, side_indexes, sow

DIFFICULTIES = ('easy', 'normal', 'hard')
SEARCH = {'normal': (2, 2_000), 'hard': (8, 20_000)}
WIN = 10_000


class _OutOfBudget(Exception):
    pass


def _evaluate(board, side):
    enemy = opponent(side)
    stores = board[STORE[side]] - board[STORE[enemy]]
    if is_finished(board):
        return (WIN if stores > 0 else -WIN if stores < 0 else 0) + stores
    # Stones still in a row usually end up with that row's owner, but they can be captured.
    rows = sum(board[i] for i in side_indexes(side)) - sum(board[i] for i in side_indexes(enemy))
    return 4 * stores + rows


def _ordered(board, mover):
    """Pits that end in the mover's store first, then the ones nearest the store."""
    pits = legal_pits(board, mover)
    return sorted(pits, key=lambda pit: (board[pit_index(mover, pit)] != PITS - pit, -pit))


def _search(board, side, mover, depth, alpha, beta, budget):
    budget[0] -= 1
    if budget[0] < 0:
        raise _OutOfBudget
    if depth == 0 or is_finished(board):
        return _evaluate(board, side)
    maximizing = mover == side
    best = -WIN * 2 if maximizing else WIN * 2
    for pit in _ordered(board, mover):
        next_board, move = sow(board, mover, pit)
        next_mover = mover if move['extra_turn'] else opponent(mover)
        value = _search(next_board, side, next_mover, depth - 1, alpha, beta, budget)
        if maximizing:
            best = max(best, value)
            alpha = max(alpha, best)
        else:
            best = min(best, value)
            beta = min(beta, best)
        if alpha >= beta:
            break
    return best


def _best_pit(board, side, pits, depth, budget):
    best_pit, best_value = pits[0], -WIN * 2
    for pit in pits:
        next_board, move = sow(board, side, pit)
        next_mover = side if move['extra_turn'] else opponent(side)
        # A strict comparison keeps the first of several equal moves, which the caller shuffled.
        value = _search(next_board, side, next_mover, depth - 1, best_value, WIN * 2, budget)
        if value > best_value:
            best_pit, best_value = pit, value
    return best_pit


def choose_pit(board, side, difficulty='normal', rng=None):
    """Choose one of the side's non-empty pits (0-5)."""
    if difficulty not in DIFFICULTIES:
        raise ValueError('Unknown computer difficulty.')
    rng = rng or SystemRandom()
    pits = legal_pits(board, side)
    if not pits:
        raise ValueError('There are no stones to play.')
    if difficulty == 'easy' or len(pits) == 1:
        return rng.choice(pits)
    rng.shuffle(pits)
    max_depth, nodes = SEARCH[difficulty]
    budget = [nodes]
    choice = pits[0]
    for depth in range(1, max_depth + 1):
        try:
            choice = _best_pit(board, side, pits, depth, budget)
        except _OutOfBudget:
            # Keep the answer of the last depth that was searched completely.
            break
    return choice
