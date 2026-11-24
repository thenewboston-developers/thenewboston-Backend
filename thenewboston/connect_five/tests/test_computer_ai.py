from copy import deepcopy
from random import Random

import pytest

from thenewboston.connect_five.constants import create_empty_board
from thenewboston.connect_five.services.computer_ai import INVENTORY_FIELDS, choose_move, legal_moves
from thenewboston.connect_five.services.rules import apply_move, check_win

EMPTY = dict.fromkeys(INVENTORY_FIELDS.values(), 0)
FULL = dict.fromkeys(INVENTORY_FIELDS.values(), 2)


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_computer_uses_only_legal_moves_and_available_specials(difficulty):
    board = create_empty_board()
    inventory = dict(FULL)
    rng = Random(27)
    for turn in range(8):
        board[14][turn] = 1
        original = deepcopy(board)
        move = choose_move(board, inventory, EMPTY, difficulty, rng)
        assert board == original
        board, _, _ = apply_move(board_state=board, player_value=2, **move)
        if field := INVENTORY_FIELDS.get(move['move_type']):
            assert inventory[field] > 0
            inventory[field] -= 1
    assert all(value >= 0 for value in inventory.values())


@pytest.mark.parametrize('difficulty', ['normal', 'hard'])
def test_tactical_computer_takes_an_immediate_special_win(difficulty):
    board = create_empty_board()
    board[7][4:7] = [2, 2, 2]
    move = choose_move(board, FULL, FULL, difficulty, Random(1))
    result, positions, _ = apply_move(board_state=board, player_value=2, **move)
    assert move['move_type'] == 'H2'
    assert check_win(board_state=result, player_value=2, positions=positions)


@pytest.mark.parametrize('difficulty', ['normal', 'hard'])
def test_tactical_computer_blocks_an_immediate_human_win(difficulty):
    board = create_empty_board()
    board[0][:4] = [1, 1, 1, 1]
    move = choose_move(board, FULL, EMPTY, difficulty, Random(2))
    result, _, _ = apply_move(board_state=board, player_value=2, **move)
    assert not any(
        check_win(board_state=reply, player_value=1, positions=positions)
        for _, reply, positions, _ in legal_moves(result, 1, EMPTY)
    )


def test_computer_does_not_use_exhausted_specials():
    board = create_empty_board()
    board[3][3] = 1
    move = choose_move(board, EMPTY, FULL, 'hard', Random(4))
    assert move['move_type'] == 'SINGLE'
