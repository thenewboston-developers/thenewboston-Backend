from random import Random

import pytest

from thenewboston.reversi.ai import choose_move
from thenewboston.reversi.rules import apply_move, count_disks, initial_board, leader, legal_moves, next_side


def play_game(black, white, seed):
    rng = Random(seed)
    board, side = initial_board(), 'black'
    while side:
        row, column = choose_move(board, side, black if side == 'black' else white, rng)
        board, _ = apply_move(board, side, row, column)
        side = next_side(board, side)
    return leader(board)


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_every_level_only_plays_legal_moves(difficulty):
    rng = Random(7)
    board, side = initial_board(), 'black'
    for _ in range(12):
        move = choose_move(board, side, difficulty, rng)
        assert move in legal_moves(board, side)
        board, _ = apply_move(board, side, *move)
        side = next_side(board, side)


def test_easy_is_random_and_unknown_levels_are_rejected():
    moves = {choose_move(initial_board(), 'black', 'easy', Random(seed)) for seed in range(40)}
    assert moves == {(2, 3), (3, 2), (4, 5), (5, 4)}
    with pytest.raises(ValueError, match='difficulty'):
        choose_move(initial_board(), 'black', 'expert')


def test_no_legal_move_is_an_error():
    board = ['b.......'] + ['........'] * 7
    with pytest.raises(ValueError, match='no legal moves'):
        choose_move(board, 'black', 'hard')


@pytest.mark.parametrize('difficulty', ['normal', 'hard'])
def test_thinking_levels_take_an_open_corner(difficulty):
    board = ['.wb.....', '.w......', '.b......', '...wb...', '...bw...', '........', '........', '........']
    assert (0, 0) in legal_moves(board, 'black')
    assert choose_move(board, 'black', difficulty, Random(1)) == (0, 0)


def exact_margin(board, side):
    """Brute-force the best final disk margin for black, with the plain rules."""
    if side is None:
        counts = count_disks(board)
        return counts['black'] - counts['white']
    margins = []
    for row, column in legal_moves(board, side):
        after, _ = apply_move(board, side, row, column)
        margins.append(exact_margin(after, next_side(after, side)))
    return max(margins) if side == 'black' else min(margins)


def test_hard_plays_the_end_of_the_game_exactly():
    rng = Random(11)
    checked = 0
    while checked < 6:
        board, side = initial_board(), 'black'
        while side and sum(row.count('.') for row in board) > 6:
            board, _ = apply_move(board, side, *rng.choice(legal_moves(board, side)))
            side = next_side(board, side)
        if not side:
            continue
        row, column = choose_move(board, side, 'hard', rng)
        after, _ = apply_move(board, side, row, column)
        assert exact_margin(after, next_side(after, side)) == exact_margin(board, side)
        checked += 1


def test_levels_are_ordered_by_strength():
    assert play_game('normal', 'easy', 3) == 'black'
    assert play_game('easy', 'normal', 4) == 'white'
    assert play_game('normal', 'hard', 6) == 'white'
