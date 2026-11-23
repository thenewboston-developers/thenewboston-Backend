from copy import deepcopy
from random import Random

import pytest

from thenewboston.backgammon.ai import choose_turn
from thenewboston.backgammon.rules import (
    apply_turn,
    initial_board,
    legal_turns,
    opponent,
    turn_outcomes,
    win_points,
    winner,
)


def board_with(white, black=None, white_bar=0, black_bar=0):
    black = {18: 15} if black is None else black
    assert not white.keys() & black.keys()
    points = [0] * 24
    for point, count in white.items():
        points[point] = count
    for point, count in black.items():
        points[point] = -count
    return {
        'points': points,
        'bar': {'white': white_bar, 'black': black_bar},
        'off': {'white': 15 - sum(white.values()) - white_bar, 'black': 15 - sum(black.values()) - black_bar},
    }


def move(source, destination, die):
    return {'from': source, 'to': destination, 'die': die}


def turn_key(turn):
    return tuple((step['from'], step['to'], step['die']) for step in turn)


def mirror(board):
    return {
        'points': [-count for count in reversed(board['points'])],
        'bar': {'white': board['bar']['black'], 'black': board['bar']['white']},
        'off': {'white': board['off']['black'], 'black': board['off']['white']},
    }


def test_initial_board_has_correct_setup_and_independent_storage():
    board = initial_board()
    assert [(point, count) for point, count in enumerate(board['points']) if count] == [
        (0, -2),
        (5, 5),
        (7, 3),
        (11, -5),
        (12, 5),
        (16, -3),
        (18, -5),
        (23, 2),
    ]
    board['points'][0] = 0
    board['bar']['white'] = 1
    assert initial_board()['points'][0] == -2
    assert initial_board()['bar']['white'] == 0


def test_bar_checkers_enter_first_and_hit_a_blot():
    board = board_with({7: 14}, {23: 1, 18: 14}, white_bar=1)
    turns = legal_turns(board, 'white', [1, 2])
    assert turns
    assert all(turn[0]['from'] == 'bar' for turn in turns)
    selected = [move('bar', 23, 1), move(23, 21, 2)]
    assert selected in turns
    result = apply_turn(board, 'white', [1, 2], selected)
    assert result['bar'] == {'white': 0, 'black': 1}
    assert result['points'][21] == 1


def test_multiple_bar_checkers_must_all_enter_before_other_moves():
    board = board_with({7: 13}, white_bar=2)
    turns = legal_turns(board, 'white', [1, 2])
    assert all([step['from'] for step in turn] == ['bar', 'bar'] for turn in turns)


def test_blocked_bar_forces_a_pass_even_with_other_mobile_checkers():
    board = board_with({7: 14}, {23: 2, 22: 2, 18: 11}, white_bar=1)
    assert legal_turns(board, 'white', [1, 2]) == [[]]
    assert apply_turn(board, 'white', [1, 2], []) == board


def test_one_bar_entry_uses_available_die_and_then_moves():
    board = board_with({7: 14}, {23: 2, 18: 13}, white_bar=1)
    turns = legal_turns(board, 'white', [1, 2])
    assert all(turn[0] == move('bar', 22, 2) for turn in turns)
    assert all(len(turn) == 2 for turn in turns)


def test_both_dice_must_be_used_when_one_order_enables_them():
    board = board_with({2: 1}, {1: 2, 18: 13})
    assert legal_turns(board, 'white', [1, 2]) == [[move(2, 0, 2), move(0, 'off', 1)]]
    with pytest.raises(ValueError, match='complete legal turn'):
        apply_turn(board, 'white', [1, 2], [move(2, 0, 2)])


def test_larger_die_required_when_either_is_playable_but_not_both():
    board = board_with({}, {17: 2, 10: 13}, white_bar=1)
    assert legal_turns(board, 'white', [1, 6]) == [[move('bar', 18, 6)]]


def test_smaller_die_allowed_when_larger_is_not_playable():
    board = board_with({}, {18: 2, 17: 2, 10: 11}, white_bar=1)
    assert legal_turns(board, 'white', [1, 6]) == [[move('bar', 23, 1)]]


def test_doubles_use_four_moves():
    board = initial_board()
    turns = legal_turns(board, 'white', [3, 3])
    assert turns
    assert all(len(turn) == 4 and all(step['die'] == 3 for step in turn) for turn in turns)


def test_doubles_use_maximum_possible_when_blocked():
    board = board_with({5: 1}, {1: 2, 18: 13})
    assert legal_turns(board, 'white', [2, 2]) == [[move(5, 3, 2)]]


def test_bearing_off_requires_every_checker_home():
    board = board_with({6: 1, 0: 1})
    turns = legal_turns(board, 'white', [1, 2])
    assert all(turn[0]['to'] != 'off' for turn in turns)
    assert [move(6, 4, 2), move(0, 'off', 1)] in turns


def test_oversized_bearoff_only_takes_furthest_checker():
    board = board_with({4: 1, 0: 1})
    turns = legal_turns(board, 'white', [6, 1])
    assert not any(turn[0] == move(0, 'off', 6) for turn in turns)
    assert [move(4, 'off', 6), move(0, 'off', 1)] in turns


def test_exact_bearoff_can_take_closer_checker_with_further_checker_present():
    board = board_with({5: 1, 1: 1})
    assert [move(1, 'off', 2), move(5, 4, 1)] in legal_turns(board, 'white', [2, 1])


def test_last_checker_must_use_larger_die_when_either_finishes():
    board = board_with({0: 1})
    assert legal_turns(board, 'white', [1, 6]) == [[move(0, 'off', 6)]]
    result = apply_turn(board, 'white', [1, 6], [move(0, 'off', 6)])
    assert winner(result) == 'white'


def test_full_move_validation_rejects_wrong_die_and_incomplete_turn():
    board = initial_board()
    valid = legal_turns(board, 'white', [3, 1])[0]
    with pytest.raises(ValueError):
        apply_turn(board, 'white', [3, 1], valid[:1])
    wrong_die = deepcopy(valid)
    wrong_die[0]['die'] = 6
    with pytest.raises(ValueError):
        apply_turn(board, 'white', [3, 1], wrong_die)
    with pytest.raises(ValueError):
        apply_turn(board, 'white', [3, 1], [])


@pytest.mark.parametrize('dice', [[], [1], [1, 2, 3], [True, 2], [1.0, 2], [0, 6], [7, 2], '12'])
def test_invalid_dice_rejected(dice):
    with pytest.raises(ValueError):
        legal_turns(initial_board(), 'white', dice)


@pytest.mark.parametrize('bad_move', [move(True, 0, 1), move(5, False, 1), move(5, 4, True), move(-1, 0, 1), {}])
def test_invalid_move_types_rejected(bad_move):
    with pytest.raises(ValueError):
        apply_turn(initial_board(), 'white', [1, 2], [bad_move])


def test_invalid_board_and_side_rejected():
    board = initial_board()
    board['points'][0] -= 1
    with pytest.raises(ValueError, match='15 checkers'):
        legal_turns(board, 'white', [1, 2])
    with pytest.raises(ValueError, match='color'):
        legal_turns(initial_board(), 'red', [1, 2])


@pytest.mark.parametrize(
    ('loser_points', 'loser_bar', 'expected'),
    [({18: 14}, 0, 1), ({18: 15}, 0, 2), ({18: 14, 5: 1}, 0, 3), ({18: 14}, 1, 3)],
)
def test_single_gammon_and_backgammon_for_both_sides(loser_points, loser_bar, expected):
    board = board_with({}, loser_points, black_bar=loser_bar)
    assert winner(board) == 'white'
    assert win_points(board, 'white') == expected
    reversed_board = mirror(board)
    assert winner(reversed_board) == 'black'
    assert win_points(reversed_board, 'black') == expected


def test_win_points_requires_actual_winner():
    assert winner(initial_board()) is None
    with pytest.raises(ValueError):
        win_points(initial_board(), 'white')


def test_all_public_transforms_preserve_inputs():
    board = initial_board()
    before = deepcopy(board)
    dice = [1, 2]
    turns = legal_turns(board, 'white', dice)
    before_turn = deepcopy(turns[0])
    result = apply_turn(board, 'white', dice, turns[0])
    outcomes = turn_outcomes(board, 'white', dice)
    assert board == before
    assert turns[0] == before_turn
    assert dice == [1, 2]
    assert outcomes
    result['points'][0] = 100
    assert board == before


def test_black_and_white_moves_are_mirrored():
    board = board_with({23: 2, 7: 4, 5: 7}, {0: 2, 13: 5, 18: 6}, white_bar=2, black_bar=2)
    for dice in ([1, 2], [3, 3], [5, 6]):
        white_turns = legal_turns(board, 'white', dice)
        expected = {
            tuple(
                (23 - source if type(source) is int else source, 23 - target if type(target) is int else target, die)
                for source, target, die in turn_key(turn)
            )
            for turn in white_turns
        }
        assert {turn_key(turn) for turn in legal_turns(mirror(board), 'black', dice)} == expected


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_computer_returns_legal_turn_for_each_difficulty(difficulty):
    board = initial_board()
    turn = choose_turn(board, 'white', [5, 3], difficulty)
    assert turn in legal_turns(board, 'white', [5, 3])
    assert apply_turn(board, 'white', [5, 3], turn)


def test_computer_handles_pass_and_takes_winning_bearoff():
    blocked = board_with({7: 14}, {23: 2, 22: 2, 18: 11}, white_bar=1)
    assert choose_turn(blocked, 'white', [1, 2]) == []
    board = board_with({1: 1})
    turn = choose_turn(board, 'white', [1, 2])
    assert winner(apply_turn(board, 'white', [1, 2], turn)) == 'white'
    with pytest.raises(ValueError, match='difficulty'):
        choose_turn(board, 'white', [1, 2], 'expert')


@pytest.mark.parametrize('seed', range(5))
def test_complete_computer_games_conserve_all_checkers(seed):
    random = Random(seed)
    board = initial_board()
    side = 'white'
    for _ in range(600):
        dice = [random.randint(1, 6), random.randint(1, 6)]
        before = deepcopy(board)
        turn = choose_turn(board, side, dice)
        board = apply_turn(board, side, dice, turn)
        assert before is not board
        for color, sign in (('white', 1), ('black', -1)):
            assert (
                sum(max(count * sign, 0) for count in board['points']) + board['bar'][color] + board['off'][color] == 15
            )
        if winner(board):
            assert win_points(board, side) in (1, 2, 3)
            break
        side = opponent(side)
    else:
        pytest.fail('The practice opponents did not complete a game.')
