"""Pure backgammon checker-play rules, using zero-based points.

White moves from point 23 towards point 0, black in the opposite direction.
A turn is submitted as a complete sequence so using fewer dice than possible,
or the smaller die when only the larger one may be used, cannot be accepted.
"""

from functools import lru_cache

SIDES = ('white', 'black')
CHECKERS = 15


def initial_board():
    points = [0] * 24
    for point, count in ((23, 2), (12, 5), (7, 3), (5, 5), (0, -2), (11, -5), (16, -3), (18, -5)):
        points[point] = count
    return {'points': points, 'bar': {'white': 0, 'black': 0}, 'off': {'white': 0, 'black': 0}}


def opponent(side):
    if side not in SIDES:
        raise ValueError('Unknown checker color.')
    return 'black' if side == 'white' else 'white'


def _validate_board(board):
    if not isinstance(board, dict):
        raise ValueError('Invalid board.')
    points = board.get('points')
    if not isinstance(points, list) or len(points) != 24:
        raise ValueError('A board must have 24 points.')
    if any(type(count) is not int or abs(count) > CHECKERS for count in points):
        raise ValueError('Invalid checker count.')
    for area in ('bar', 'off'):
        values = board.get(area)
        if not isinstance(values, dict) or any(
            type(values.get(side)) is not int or not 0 <= values[side] <= CHECKERS for side in SIDES
        ):
            raise ValueError('Invalid checker count.')
    for side, sign in (('white', 1), ('black', -1)):
        total = sum(max(count * sign, 0) for count in points) + board['bar'][side] + board['off'][side]
        if total != CHECKERS:
            raise ValueError('Each player must have 15 checkers.')


def _state(board):
    return (
        tuple(board['points']),
        board['bar']['white'],
        board['bar']['black'],
        board['off']['white'],
        board['off']['black'],
    )


def _board(state):
    points, white_bar, black_bar, white_off, black_off = state
    return {
        'points': list(points),
        'bar': {'white': white_bar, 'black': black_bar},
        'off': {'white': white_off, 'black': black_off},
    }


def _single_moves(state, side, die):
    points, white_bar, black_bar, _, _ = state
    sign = 1 if side == 'white' else -1
    on_bar = white_bar if side == 'white' else black_bar
    if on_bar:
        destination = 24 - die if side == 'white' else die - 1
        if points[destination] * sign >= -1:
            return [('bar', destination, die)]
        return []

    occupied = [point for point, count in enumerate(points) if count * sign > 0]
    home_ready = all(point < 6 if side == 'white' else point >= 18 for point in occupied)
    moves = []
    for source in occupied:
        destination = source - sign * die
        if 0 <= destination < 24:
            if points[destination] * sign >= -1:
                moves.append((source, destination, die))
        elif home_ready:
            distance = source + 1 if side == 'white' else 24 - source
            furthest = max(occupied) if side == 'white' else min(occupied)
            if die == distance or (die > distance and source == furthest):
                moves.append((source, 'off', die))
    return moves


def _step(state, side, move):
    points, white_bar, black_bar, white_off, black_off = state
    points = list(points)
    sign = 1 if side == 'white' else -1
    source, destination, _ = move
    if source == 'bar':
        if side == 'white':
            white_bar -= 1
        else:
            black_bar -= 1
    else:
        points[source] -= sign
    if destination == 'off':
        if side == 'white':
            white_off += 1
        else:
            black_off += 1
    else:
        if points[destination] == -sign:
            points[destination] = 0
            if side == 'white':
                black_bar += 1
            else:
                white_bar += 1
        points[destination] += sign
    return (tuple(points), white_bar, black_bar, white_off, black_off)


def _legal_sequences(board, side, dice):
    _validate_board(board)
    opponent(side)
    if (
        not isinstance(dice, (list, tuple))
        or len(dice) != 2
        or any(type(die) is not int or not 1 <= die <= 6 for die in dice)
    ):
        raise ValueError('A roll must contain two dice from 1 to 6.')
    remaining = tuple([dice[0]] * 4 if dice[0] == dice[1] else sorted(dice, reverse=True))

    @lru_cache(maxsize=None)
    def visit(state, unused):
        if not unused or state[3] == CHECKERS or state[4] == CHECKERS:
            return ((),)
        sequences = []
        for die in dict.fromkeys(unused):
            rest = list(unused)
            rest.remove(die)
            for move in _single_moves(state, side, die):
                for tail in visit(_step(state, side, move), tuple(rest)):
                    sequences.append((move, *tail))
        return tuple(sequences) if sequences else ((),)

    sequences = visit(_state(board), remaining)
    maximum = max(map(len, sequences))
    sequences = [sequence for sequence in sequences if len(sequence) == maximum]
    if maximum == 1 and dice[0] != dice[1]:
        highest = max(sequence[0][2] for sequence in sequences)
        sequences = [sequence for sequence in sequences if sequence[0][2] == highest]
    return sequences


def _move_dict(move):
    return {'from': move[0], 'to': move[1], 'die': move[2]}


def legal_turns(board, side, dice):
    """Return every complete legal move order; ``[[]]`` means a forced pass."""
    return [[_move_dict(move) for move in sequence] for sequence in _legal_sequences(board, side, dice)]


def turn_outcomes(board, side, dice):
    """Return a representative legal turn and board for each distinct outcome.

    Computer evaluation need not repeatedly evaluate equivalent move orders.
    The public legal-turn list still retains every valid order for human input.
    """
    sequences = _legal_sequences(board, side, dice)
    outcomes = {}
    initial = _state(board)
    for sequence in sequences:
        state = initial
        for move in sequence:
            state = _step(state, side, move)
        outcomes.setdefault(state, sequence)
    return [([_move_dict(move) for move in sequence], _board(state)) for state, sequence in outcomes.items()]


def apply_turn(board, side, dice, moves):
    """Validate an entire turn and return a new board without mutating input."""
    if not isinstance(moves, list) or len(moves) > 4:
        raise ValueError('Invalid move sequence.')
    sequence = []
    for move in moves:
        if not isinstance(move, dict) or set(move) != {'from', 'to', 'die'}:
            raise ValueError('Each move requires from, to, and die.')
        source, destination, die = move['from'], move['to'], move['die']
        if not (source == 'bar' or type(source) is int and 0 <= source < 24):
            raise ValueError('Invalid move origin.')
        if not (destination == 'off' or type(destination) is int and 0 <= destination < 24):
            raise ValueError('Invalid move destination.')
        if type(die) is not int or not 1 <= die <= 6:
            raise ValueError('Invalid move die.')
        sequence.append((source, destination, die))
    if tuple(sequence) not in _legal_sequences(board, side, dice):
        raise ValueError('Play a complete legal turn using as many dice as possible.')
    state = _state(board)
    for move in sequence:
        state = _step(state, side, move)
    return _board(state)


def winner(board):
    _validate_board(board)
    return next((side for side in SIDES if board['off'][side] == CHECKERS), None)


def win_points(board, winner_side):
    """Single, gammon, or backgammon points, before the doubling multiplier."""
    if winner(board) != winner_side:
        raise ValueError('The player has not borne off all checkers.')
    loser = opponent(winner_side)
    if board['off'][loser]:
        return 1
    home = range(6) if winner_side == 'white' else range(18, 24)
    loser_sign = -1 if loser == 'black' else 1
    if board['bar'][loser] or any(board['points'][point] * loser_sign > 0 for point in home):
        return 3
    return 2
