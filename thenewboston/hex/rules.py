"""Hex on a rhombus of size x size hexagonal cells, stored row by row.

Red moves first and wins by joining the top row to the bottom row. Blue wins by
joining the left column to the right column. A full board always holds exactly
one such chain, so a game cannot be drawn.

Each cell touches up to six others: its two row neighbours, the two cells above
(same column and the next one) and the two below (previous column and the same).
"""

from collections import deque
from functools import lru_cache

EMPTY, RED, BLUE = 0, 1, 2
SIZES = (7, 9, 11, 13)
STONES = {'red': RED, 'blue': BLUE}
_OFFSETS = ((-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0))


def empty_board(size):
    return [EMPTY] * (size * size)


def opponent(side):
    return 'blue' if side == 'red' else 'red'


@lru_cache(maxsize=None)
def neighbors(size):
    """For every cell, the cells it touches."""
    table = []
    for cell in range(size * size):
        row, column = divmod(cell, size)
        table.append(
            tuple(
                (row + dr) * size + column + dc
                for dr, dc in _OFFSETS
                if 0 <= row + dr < size and 0 <= column + dc < size
            )
        )
    return tuple(table)


@lru_cache(maxsize=None)
def edges(size, side):
    """The cells of the two edges a side has to join."""
    if side == 'red':
        return tuple(range(size)), tuple(range(size * (size - 1), size * size))
    return tuple(range(0, size * size, size)), tuple(range(size - 1, size * size, size))


def mirror(size, cell):
    """The cell that means to Blue what `cell` means to Red, and the reverse."""
    row, column = divmod(cell, size)
    return column * size + row


def winning_path(board, size, side):
    """The shortest chain of a side's stones joining its two edges, or None."""
    stone = STONES[side]
    start, end = edges(size, side)
    goal = set(end)
    adjacent = neighbors(size)
    previous = {cell: None for cell in start if board[cell] == stone}
    queue = deque(previous)
    while queue:
        cell = queue.popleft()
        if cell in goal:
            path = []
            while cell is not None:
                path.append(cell)
                cell = previous[cell]
            return path[::-1]
        for other in adjacent[cell]:
            if board[other] == stone and other not in previous:
                previous[other] = cell
                queue.append(other)
    return None


def place(board, size, side, cell):
    """Return the board after a side puts a stone on an empty cell."""
    if type(cell) is not int or not 0 <= cell < size * size:
        raise ValueError('Choose a cell on the board.')
    if board[cell] != EMPTY:
        raise ValueError('That cell is already taken. Choose an empty cell.')
    updated = board.copy()
    updated[cell] = STONES[side]
    return updated


def swap(board, size):
    """Blue takes over Red's opening stone: it turns blue and moves to its mirror cell.

    The players keep their colours and edges, and Red moves next. Returns the
    board, the cell the red stone was on and the cell the blue stone is on.
    """
    stones = [cell for cell, stone in enumerate(board) if stone != EMPTY]
    if len(stones) != 1 or board[stones[0]] != RED:
        raise ValueError('The opening can only be swapped straight after the first stone.')
    origin = stones[0]
    target = mirror(size, origin)
    updated = empty_board(size)
    updated[target] = BLUE
    return updated, origin, target
