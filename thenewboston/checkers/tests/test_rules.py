from random import Random

import pytest

from thenewboston.checkers.ai import choose_move
from thenewboston.checkers.rules import apply_move, initial_board, legal_moves, opponent, position_key


def board_with(pieces):
    board = [0] * 64
    for square, piece in pieces.items():
        board[square] = piece
    return board


def test_initial_board_has_twelve_each_on_dark_squares_and_seven_moves():
    board = initial_board()
    assert board.count(1) == board.count(-1) == 12
    assert all((square // 8 + square % 8) % 2 for square, piece in enumerate(board) if piece)
    assert len(legal_moves(board, 'white')) == len(legal_moves(board, 'black')) == 7
    assert position_key(board, 'white') != position_key(board, 'black')


def test_men_move_and_capture_only_forward_while_kings_can_move_backward():
    board = board_with({26: 1, 35: -1})
    assert [26, 44] not in legal_moves(board, 'white')
    board[26] = 2
    assert legal_moves(board, 'white') == [[26, 44]]


def test_capture_is_mandatory_for_every_piece_and_chain_cannot_stop_early():
    board = board_with({42: 1, 46: 1, 35: -1, 21: -1, 1: -1})
    assert legal_moves(board, 'white') == [[42, 28, 14]]
    for path in [[46, 37], [42, 28]]:
        with pytest.raises(ValueError):
            apply_move(board, 'white', path)
    updated, captured = apply_move(board, 'white', [42, 28, 14])
    assert captured == [35, 21]
    assert updated[14] == 1 and updated.count(-1) == 1
    assert board[42] == 1 and board[35] == -1  # caller's board is immutable


def test_any_complete_capture_chain_is_allowed_without_maximum_capture_rule():
    board = board_with({42: 1, 33: -1, 35: -1, 21: -1})
    assert sorted(legal_moves(board, 'white')) == [[42, 24], [42, 28, 14]]


def test_crowning_ends_capture_turn_and_simple_move_crowns():
    board = board_with({17: 1, 10: -1, 12: -1})
    assert legal_moves(board, 'white') == [[17, 3]]
    updated, captured = apply_move(board, 'white', [17, 3])
    assert updated[3] == 2 and captured == [10] and updated[12] == -1
    with pytest.raises(ValueError):
        apply_move(board, 'white', [17, 3, 21])
    updated, _ = apply_move(board_with({49: -1, 1: 1}), 'black', [49, 56])
    assert updated[56] == -2


def test_blocked_player_has_no_moves_and_board_edges_do_not_wrap():
    assert legal_moves(board_with({1: 1, 62: -1}), 'white') == []
    assert legal_moves(board_with({1: 1, 62: -1}), 'black') == []
    assert legal_moves(board_with({40: 1}), 'white') == [[40, 33]]


@pytest.mark.parametrize('path', [[], [42], [42, 100], [42, -1], [42, 33, 24], [True, 10], ['42', 33], None])
def test_malformed_or_illegal_paths_are_rejected(path):
    with pytest.raises(ValueError):
        apply_move(initial_board(), 'white', path)


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_computer_returns_legal_complete_turn(difficulty):
    board = board_with({42: 1, 35: -1, 21: -1})
    assert choose_move(board, 'white', difficulty) == [42, 28, 14]
    assert choose_move(initial_board(), 'black', difficulty) in legal_moves(initial_board(), 'black')
    assert choose_move([0] * 64, 'black', difficulty) is None


def test_many_legal_turns_preserve_piece_and_square_invariants():
    random = Random(18)
    for _ in range(8):
        board, side = initial_board(), 'white'
        for _ in range(150):
            choices = legal_moves(board, side)
            if not choices:
                break
            previous_count = sum(bool(piece) for piece in board)
            board, captures = apply_move(board, side, random.choice(choices))
            assert sum(bool(piece) for piece in board) == previous_count - len(captures)
            assert all((square // 8 + square % 8) % 2 for square, piece in enumerate(board) if piece)
            assert set(board) <= {0, 1, -1, 2, -2}
            side = opponent(side)


def test_king_capture_loop_can_return_to_origin_without_recapturing_a_piece():
    board = board_with({42: 2, 33: -1, 17: -1, 19: -1, 35: -1})
    path = [42, 24, 10, 28, 42]
    assert path in legal_moves(board, 'white')
    updated, captured = apply_move(board, 'white', path)
    assert updated[42] == 2 and len(captured) == len(set(captured)) == 4
    assert sum(bool(piece) for piece in updated) == 1
