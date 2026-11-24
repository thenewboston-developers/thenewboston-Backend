"""Dots and Boxes on a square board of ``size`` by ``size`` boxes.

Lines are numbered row by row: first every horizontal line from the top edge
down to the bottom edge, then every vertical line, left to right within each
row of boxes. Boxes are numbered row by row from the top left.

Drawing the fourth side of a box claims it and keeps the turn; any other line
passes the turn. The game ends when every box is claimed.
"""

from functools import lru_cache

SIZES = (3, 4, 5)
SIDE_NUMBERS = {'blue': 1, 'red': 2}


def opponent(side):
    return 'red' if side == 'blue' else 'blue'


def line_count(size):
    return 2 * size * (size + 1)


@lru_cache(maxsize=None)
def box_lines(size):
    """The four lines around each box: top, bottom, left, right."""
    horizontal = size * (size + 1)
    return tuple(
        (
            row * size + column,
            (row + 1) * size + column,
            horizontal + row * (size + 1) + column,
            horizontal + row * (size + 1) + column + 1,
        )
        for row in range(size)
        for column in range(size)
    )


@lru_cache(maxsize=None)
def line_boxes(size):
    """The one or two boxes that each line borders."""
    bordering = [[] for _ in range(line_count(size))]
    for box, lines in enumerate(box_lines(size)):
        for line in lines:
            bordering[line].append(box)
    return tuple(tuple(boxes) for boxes in bordering)


def initial_lines(size):
    return [0] * line_count(size)


def initial_boxes(size):
    return [0] * (size * size)


def apply_move(size, lines, boxes, side, line):
    """Draw one line for ``side``; return the new lines, new boxes and the boxes it completed."""
    if type(line) is not int or not 0 <= line < line_count(size) or lines[line]:
        raise ValueError('Choose a line that has not been drawn yet.')
    owner = SIDE_NUMBERS[side]
    lines = [*lines]
    lines[line] = owner
    completed = [box for box in line_boxes(size)[line] if all(lines[edge] for edge in box_lines(size)[box])]
    boxes = [*boxes]
    for box in completed:
        boxes[box] = owner
    return lines, boxes, completed
