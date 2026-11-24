"""Computer play for Dots and Boxes.

Easy takes any box on offer and otherwise draws at random. Normal also avoids
handing boxes over for as long as it can, then gives away as few as possible.
Hard adds chain control (declining the last two boxes of a chain to keep the
upper hand) and an exact search of the position whenever it is small enough.

A board is searched as a bitmask of drawn lines. What is still to be won from
a position depends only on which lines are drawn, never on who drew them.
"""

from functools import lru_cache
from random import choice

from .rules import box_lines, line_boxes, line_count

SEARCH_NODE_LIMIT = 20000
# Searching earlier than this rarely finishes: every extra safe line multiplies the endings to solve.
SEARCH_SAFE_LINE_LIMIT = 4


class TurnSearch:
    """Positions solved during one computer turn, and the nodes that turn may still spend."""

    def __init__(self, nodes=SEARCH_NODE_LIMIT):
        self.nodes = nodes
        self.solved = {}


class _OutOfNodes(Exception):
    pass


@lru_cache(maxsize=None)
def _geometry(size):
    box_masks = tuple(sum(1 << line for line in lines) for lines in box_lines(size))
    return box_masks, line_boxes(size), line_count(size)


def _classify(mask, size):
    """Sides drawn per box, and the open lines split into captures, safe lines and sacrifices."""
    box_masks, bordering, total = _geometry(size)
    sides = [(mask & box_mask).bit_count() for box_mask in box_masks]
    captures, safe, sacrifices = [], [], []
    for line in range(total):
        if mask >> line & 1:
            continue
        most = max(sides[box] for box in bordering[line])
        if most == 3:
            captures.append(line)
        elif most == 2:
            sacrifices.append(line)
        else:
            safe.append(line)
    return sides, captures, safe, sacrifices


def _completed(mask, size, line):
    """Number of boxes that drawing this line on this position completes."""
    box_masks, bordering, _ = _geometry(size)
    drawn = mask | 1 << line
    return sum((drawn & box_masks[box]) == box_masks[box] for box in bordering[line])


def _double_deals(mask, size, sides, sacrifices):
    """Lines that decline boxes on offer by leaving two of them to be taken with a single line.

    Box A has three sides, its neighbour B has two, and they share A's open side. Drawing B's
    other open side leaves the pair for the opponent, who then has to move again afterwards.
    """
    box_masks, bordering, total = _geometry(size)
    lines = []
    for line in sacrifices:
        for box in bordering[line]:
            if sides[box] != 2:
                continue
            others = box_masks[box] & ~mask & ~(1 << line)
            shared = others.bit_length() - 1
            if any(sides[neighbour] == 3 for neighbour in bordering[shared] if neighbour != box):
                lines.append(line)
                break
    return lines


def _candidates(mask, size):
    """Lines worth considering: never give a box away while a safe line or a capture exists."""
    sides, captures, safe, sacrifices = _classify(mask, size)
    if captures:
        return captures + _double_deals(mask, size, sides, sacrifices)
    return safe or sacrifices


def _solve(mask, size, search):
    """Boxes the player to move wins from here minus the boxes the other player wins."""
    solved = search.solved.get(mask)
    if solved is not None:
        return solved[0]
    if mask == (1 << line_count(size)) - 1:
        return 0
    search.nodes -= 1
    if search.nodes < 0:
        raise _OutOfNodes
    best, best_lines = None, []
    for line in _candidates(mask, size):
        gained = _completed(mask, size, line)
        rest = _solve(mask | 1 << line, size, search)
        margin = gained + rest if gained else -rest
        if best is None or margin > best:
            best, best_lines = margin, [line]
        elif margin == best:
            best_lines.append(line)
    search.solved[mask] = (best, best_lines)
    return best


def _given_away(mask, size, line):
    """Boxes the opponent can take in a row once this line is drawn."""
    mask |= 1 << line
    taken = 0
    while True:
        captures = _classify(mask, size)[1]
        if not captures:
            return taken
        taken += _completed(mask, size, captures[0])
        mask |= 1 << captures[0]


def _cheapest_sacrifices(mask, size, sacrifices):
    costs = {line: _given_away(mask, size, line) for line in sacrifices}
    lowest = min(costs.values())
    return [line for line in sacrifices if costs[line] == lowest]


def _hard_line(mask, size, search):
    sides, captures, safe, sacrifices = _classify(mask, size)
    candidates = _candidates(mask, size)
    if len(candidates) == 1:
        return candidates[0]
    if len(safe) <= SEARCH_SAFE_LINE_LIMIT and search.nodes > 0:
        try:
            _solve(mask, size, search)
            return choice(search.solved[mask][1])
        except _OutOfNodes:
            # Too large to solve this turn; the rules of thumb below take over.
            search.nodes = 0
    if captures:
        if not safe:
            # Everything on offer is the tail of a chain (two boxes) or of a loop (four). Give it
            # up only when more than that is left to win with the opponent forced to move first.
            on_offer = _given_away(mask, size, captures[0]) + _completed(mask, size, captures[0])
            remaining = sum(1 for drawn in sides if drawn < 4) - on_offer
            declines = [
                line
                for line in _double_deals(mask, size, sides, sacrifices)
                if on_offer in (2, 4) and _given_away(mask, size, line) == on_offer
            ]
            if declines and remaining > on_offer:
                return choice(declines)
        return choice(captures)
    if safe:
        return choice(safe)
    cheapest = _cheapest_sacrifices(mask, size, sacrifices)
    # Splitting a pair down the middle leaves the opponent no way to decline it.
    _, bordering, _ = _geometry(size)
    split = [line for line in cheapest if sum(sides[box] == 2 for box in bordering[line]) == 2]
    return choice(split or cheapest)


def plan_turn(size, lines, difficulty):
    """Every line the computer draws in one turn: it keeps drawing for as long as it completes a box."""
    lines = [*lines]
    search = TurnSearch()
    planned = []
    while 0 in lines:
        line = choose_line(size, lines, difficulty, search)
        mask = sum(1 << drawn for drawn, owner in enumerate(lines) if owner)
        planned.append(line)
        lines[line] = 1
        if not _completed(mask, size, line):
            break
    return planned


def choose_line(size, lines, difficulty, search=None):
    """Pick an open line for the computer. Pass the same ``search`` for every line of one turn."""
    mask = sum(1 << line for line, owner in enumerate(lines) if owner)
    if difficulty == 'hard':
        return _hard_line(mask, size, search or TurnSearch())
    _, captures, safe, sacrifices = _classify(mask, size)
    if captures:
        return choice(captures)
    if difficulty == 'easy':
        return choice(safe + sacrifices)
    return choice(safe or _cheapest_sacrifices(mask, size, sacrifices))
