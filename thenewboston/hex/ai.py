"""A Hex opponent built on two-distance, cheap enough for a small server.

The two-distance of an empty cell from an edge is one more than the second
lowest two-distance among the cells around it, where cells joined by a chain of
the side's own stones count as being next to each other. Asking for the second
lowest means one blocking stone cannot spoil the route, so bridges and blocks
from a distance show up in the score where a plain shortest path misses them.
A cell's potential is the sum of its two-distances from both of a side's edges,
and a side's potential is the lowest one on the board.

Easy plays a random cell on either side's shortest path. Normal plays one of the
moves that leave it the best potential. Hard searches three moves deep, trying
only the cells both sides want most, which caps a move at 517 evaluations. All
levels finish a connection that is one stone away, and normal and hard always
stop one.
"""

from collections import deque
from random import Random

from .rules import EMPTY, STONES, edges, neighbors, opponent

BLOCKED = 10**6
WON = 10**6
HARD_DEPTH = 3
ROOT_BRANCHES = 12
INNER_BRANCHES = 6
NORMAL_SLACK = 100  # normal also plays moves up to one stone worse than its best


def _distances(board, size, side, edge):
    """Stones a side still needs to reach every cell from one of its edges, the cell included."""
    own = STONES[side]
    adjacent = neighbors(size)
    distance = [BLOCKED] * (size * size)
    queue = deque()
    for cell in edges(size, side)[edge]:
        stone = board[cell]
        if stone == own:
            distance[cell] = 0
            queue.appendleft(cell)
        elif stone == EMPTY:
            distance[cell] = 1
            queue.append(cell)
    while queue:
        cell = queue.popleft()
        base = distance[cell]
        for other in adjacent[cell]:
            stone = board[other]
            if stone == own:
                if base < distance[other]:
                    distance[other] = base
                    queue.appendleft(other)
            elif stone == EMPTY and base + 1 < distance[other]:
                distance[other] = base + 1
                queue.append(other)
    return distance


def shortest_path(board, size, side):
    """How many more stones a side needs to join its edges, and the empty cells on its shortest paths."""
    own = STONES[side]
    from_start = _distances(board, size, side, 0)
    from_end = _distances(board, size, side, 1)
    needed = BLOCKED
    for cell, stone in enumerate(board):
        if stone == EMPTY or stone == own:
            needed = min(needed, from_start[cell] + from_end[cell] - (stone == EMPTY))
    if needed >= BLOCKED:
        return BLOCKED, set()
    return needed, {
        cell for cell, stone in enumerate(board) if stone == EMPTY and from_start[cell] + from_end[cell] - 1 == needed
    }


def _two_distances(board, size, side):
    """The two-distance of every reachable empty cell from each of a side's edges."""
    own = STONES[side]
    adjacent = neighbors(size)
    # Empty cells around each chain of the side's stones.
    chain_of, borders = {}, []
    for cell, stone in enumerate(board):
        if stone != own or cell in chain_of:
            continue
        chain_of[cell] = len(borders)
        border, stack = set(), [cell]
        while stack:
            for other in adjacent[stack.pop()]:
                if board[other] == EMPTY:
                    border.add(other)
                elif board[other] == own and other not in chain_of:
                    chain_of[other] = len(borders)
                    stack.append(other)
        borders.append(border)
    around = {}
    for cell, stone in enumerate(board):
        if stone != EMPTY:
            continue
        cells = set()
        for other in adjacent[cell]:
            if board[other] == EMPTY:
                cells.add(other)
            elif board[other] == own:
                cells |= borders[chain_of[other]]
        cells.discard(cell)
        around[cell] = cells
    result = []
    for edge in edges(size, side):
        touching = set()
        for cell in edge:
            if board[cell] == EMPTY:
                touching.add(cell)
            elif board[cell] == own:
                touching |= borders[chain_of[cell]]
        distance = dict.fromkeys(touching, 1)
        settled = dict.fromkeys(around, 0)
        queue = deque(touching)
        # Cells leave the queue in order of distance, so the second settled neighbour is the second lowest.
        while queue:
            cell = queue.popleft()
            for other in around[cell]:
                if other not in distance:
                    settled[other] += 1
                    if settled[other] == 2:
                        distance[other] = distance[cell] + 1
                        queue.append(other)
        result.append(distance)
    return result


def _potentials(board, size, side):
    first, second = _two_distances(board, size, side)
    return {cell: distance + second[cell] for cell, distance in first.items() if cell in second}


def _evaluate(board, size, side):
    """A side's score in hundredths of a stone, and the empty cells in the order both sides want them."""
    far = 4 * size
    own = _potentials(board, size, side)
    other = _potentials(board, size, opponent(side))
    own_best = min(own.values(), default=far)
    other_best = min(other.values(), default=far)
    # With equal potentials, the side with more cells that reach it has more ways through.
    ways = sum(value == own_best for value in own.values()) - sum(value == other_best for value in other.values())
    cells = [cell for cell, stone in enumerate(board) if stone == EMPTY]
    cells.sort(key=lambda cell: own.get(cell, far) + other.get(cell, far))
    return 100 * (other_best - own_best) + max(-50, min(50, ways)), cells


def _search(board, size, side, depth, alpha, beta):
    """The score of the side to move after best play by both sides, `depth` moves deep."""
    needed, _ = shortest_path(board, size, side)
    if needed == 1:
        return WON + depth
    other = opponent(side)
    other_needed, other_path = shortest_path(board, size, other)
    score, cells = _evaluate(board, size, side)
    if depth == 0:
        return score
    if other_needed == 1:
        if len(other_path) > 1:
            return -WON - depth
        cells = list(other_path)
    value = -2 * WON
    for cell in cells[:INNER_BRANCHES]:
        board[cell] = STONES[side]
        try:
            value = max(value, -_search(board, size, other, depth - 1, -beta, -alpha))
        finally:
            board[cell] = EMPTY
        alpha = max(alpha, value)
        if alpha >= beta:
            break
    return value


def choose_move(board, size, side, difficulty, rng=None):
    """The cell the computer plays, or None when the board is full."""
    rng = rng or Random()
    board = list(board)
    empty = [cell for cell, stone in enumerate(board) if stone == EMPTY]
    if not empty:
        return None
    other = opponent(side)
    needed, own_path = shortest_path(board, size, side)
    if needed == 1:
        return rng.choice(sorted(own_path))
    other_needed, other_path = shortest_path(board, size, other)
    if difficulty == 'easy':
        if other_needed == 1 and rng.random() < 0.5:
            return rng.choice(sorted(other_path))
        return rng.choice(sorted(own_path | other_path) or empty)
    if other_needed == 1:
        return rng.choice(sorted(other_path))
    depth, slack = (HARD_DEPTH, 0) if difficulty == 'hard' else (1, NORMAL_SLACK)
    _, cells = _evaluate(board, size, side)
    best, scored = -2 * WON, []
    for cell in cells[:ROOT_BRANCHES]:
        board[cell] = STONES[side]
        try:
            # The window reaches just below the moves still wanted, so those keep their exact scores.
            value = -_search(board, size, other, depth - 1, -2 * WON, slack + 1 - best)
        finally:
            board[cell] = EMPTY
        scored.append((value, cell))
        best = max(best, value)
    return rng.choice([cell for value, cell in scored if value >= best - slack])
