"""A bounded, local computer opponent for free practice games.

Easy plays a random legal move. Normal takes the move that leaves the best
position by square value and mobility. Hard searches a few moves ahead and
plays the last moves of the game exactly. Every search is bounded by depth,
so a turn stays cheap on a small worker.
"""

from random import SystemRandom

from .rules import BOARD_SIZE, flips_mask, moves_mask, to_bits

DIFFICULTIES = ('easy', 'normal', 'hard')
SEARCH_DEPTH = 4
EXACT_EMPTIES = 8
WIN = 100000

CORNERS = 0x8100000000000081
EDGES = 0xFF818181818181FF & ~CORNERS
# For each corner: (corner, diagonal neighbour, the two edge neighbours).
CORNER_REGIONS = (
    (1 << 0, 1 << 9, 1 << 1 | 1 << 8),
    (1 << 7, 1 << 14, 1 << 6 | 1 << 15),
    (1 << 56, 1 << 49, 1 << 48 | 1 << 57),
    (1 << 63, 1 << 54, 1 << 55 | 1 << 62),
)
# Likely-strong squares first, so alpha-beta cuts off early.
MOVE_ORDER = sorted(
    (1 << index for index in range(64)),
    key=lambda bit: (not bit & CORNERS, not bit & EDGES, any(bit & (x | c) for _, x, c in CORNER_REGIONS)),
)


def _evaluate(own, other, own_moves):
    """Static value of a position for the side to move, which has `own_moves` available."""
    other_moves = moves_mask(other, own)
    score = 12 * (own_moves.bit_count() - other_moves.bit_count())
    score += 4 * ((own & EDGES).bit_count() - (other & EDGES).bit_count())
    for corner, diagonal, edges in CORNER_REGIONS:
        if own & corner:
            score += 120
        elif other & corner:
            score -= 120
        else:
            # Squares next to an empty corner give that corner away.
            score -= 45 * (bool(own & diagonal) - bool(other & diagonal))
            score -= 18 * ((own & edges).bit_count() - (other & edges).bit_count())
    empties = 64 - (own | other).bit_count()
    if empties <= 16:
        # Disk count starts to matter once the board fills up.
        score += (17 - empties) * (own.bit_count() - other.bit_count()) // 4
    return score


def _final(own, other):
    difference = own.bit_count() - other.bit_count()
    return (WIN + difference) if difference > 0 else (difference - WIN) if difference < 0 else 0


def _search(own, other, depth, alpha, beta, passed=False):
    """Negamax with alpha-beta. A depth of None searches to the end of the game."""
    moves = moves_mask(own, other)
    if not moves:
        if passed:
            return _final(own, other)
        return -_search(other, own, depth, -beta, -alpha, True)
    if depth == 0:
        return _evaluate(own, other, moves)
    best = -WIN * 2
    for move in MOVE_ORDER:
        if not moves & move:
            continue
        flipped = flips_mask(own, other, move)
        score = -_search(other & ~flipped, own | move | flipped, depth and depth - 1, -beta, -alpha)
        if score > best:
            best = score
            if best > alpha:
                alpha = best
                if alpha >= beta:
                    break
    return best


def choose_move(board, side, difficulty='normal', rng=None):
    """Choose a legal (row, column) for `side`. Ties are broken at random."""
    if difficulty not in DIFFICULTIES:
        raise ValueError('Unknown computer difficulty.')
    rng = rng or SystemRandom()
    black, white = to_bits(board)
    own, other = (black, white) if side == 'black' else (white, black)
    moves = moves_mask(own, other)
    candidates = [move for move in MOVE_ORDER if moves & move]
    if not candidates:
        raise ValueError('There are no legal moves.')
    if difficulty == 'easy':
        best_moves = candidates
    else:
        empties = 64 - (own | other).bit_count()
        if difficulty == 'normal':
            depth = 0
        else:
            # The move itself is the first ply of the search.
            depth = None if empties <= EXACT_EMPTIES else SEARCH_DEPTH - 1
        scored = []
        for move in candidates:
            flipped = flips_mask(own, other, move)
            # A full window keeps every score exact, so equal moves can be told apart.
            score = -_search(other & ~flipped, own | move | flipped, depth, -WIN * 2, WIN * 2)
            scored.append((score, move))
        best = max(score for score, _ in scored)
        best_moves = [move for score, move in scored if score == best]
    return divmod(rng.choice(best_moves).bit_length() - 1, BOARD_SIZE)
