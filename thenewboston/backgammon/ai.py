"""A bounded, local heuristic opponent for free practice games.

This is not a tournament-strength engine. Normal evaluates racing, structure,
and exposure; hard additionally checks sampled opponent replies.
"""

from secrets import choice

from .rules import opponent, turn_outcomes

DIFFICULTIES = ('easy', 'normal', 'hard')


def pip_count(board, side):
    sign = 1 if side == 'white' else -1
    return board['bar'][side] * 25 + sum(
        max(count * sign, 0) * (point + 1 if side == 'white' else 24 - point)
        for point, count in enumerate(board['points'])
    )


def _position_value(board, side):
    enemy = opponent(side)
    sign = 1 if side == 'white' else -1
    points = board['points']
    if board['off'][side] == 15:
        return 10000
    if board['off'][enemy] == 15:
        return -10000
    value = 12 * board['off'][side] - 12 * board['off'][enemy]
    value += (pip_count(board, enemy) - pip_count(board, side)) * 0.12
    value += 4 * board['bar'][enemy] - 4 * board['bar'][side]
    for point, count in enumerate(points):
        ours = count * sign
        if ours >= 2:
            home_point = point < 6 if side == 'white' else point >= 18
            value += 1.7 if home_point else 0.8
            value -= max(ours - 4, 0) * 0.15
        elif ours == 1:
            # Exposed blots are more costly while an enemy checker can reach them.
            attacks = 0
            for die in range(1, 7):
                source = point - sign * die
                if 0 <= source < 24 and points[source] * sign < 0:
                    attacks += 1
            entry = 24 - point if enemy == 'white' else point + 1
            if board['bar'][enemy] and 1 <= entry <= 6:
                attacks += 1
            value -= attacks * 0.9
    return value


def choose_turn(board, side, dice, difficulty='normal'):
    """Choose a legal full turn without using or influencing future dice."""
    if difficulty not in DIFFICULTIES:
        raise ValueError('Unknown computer difficulty.')
    outcomes = turn_outcomes(board, side, dice)
    if difficulty == 'easy':
        return choice(outcomes)[0]

    ranked = sorted(outcomes, key=lambda outcome: _position_value(outcome[1], side), reverse=True)
    if difficulty == 'normal' or len(ranked) == 1:
        return ranked[0][0]

    # A fixed-size shortlist and sample keep response time bounded even on a
    # small worker. These are hypothetical replies, never the next actual roll.
    enemy = opponent(side)
    samples = ((1, 2), (3, 4), (5, 6), (3, 3))

    def with_replies(outcome):
        _, next_board = outcome
        value = _position_value(next_board, side)
        if value >= 10000:
            return value
        reply_values = []
        for roll in samples:
            reply = max(
                turn_outcomes(next_board, enemy, roll), key=lambda candidate: _position_value(candidate[1], enemy)
            )
            reply_values.append(_position_value(reply[1], side))
        return value * 0.4 + sum(reply_values) / len(reply_values) * 0.6

    return max(ranked[:4], key=with_replies)[0]
