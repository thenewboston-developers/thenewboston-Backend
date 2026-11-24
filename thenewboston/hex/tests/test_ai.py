from random import Random
from unittest.mock import patch

import pytest

from thenewboston.hex import ai
from thenewboston.hex.ai import choose_move, shortest_path
from thenewboston.hex.rules import EMPTY, SIZES, STONES, empty_board, opponent, place, winning_path
from thenewboston.hex.tests.test_rules import board_with, column, row_cells

LEVELS = ['easy', 'normal', 'hard']


def play(size, red, blue, seed):
    rng = Random(seed)
    board, side = empty_board(size), 'red'
    while True:
        cell = choose_move(board, size, side, red if side == 'red' else blue, rng)
        board = place(board, size, side, cell)
        if winning_path(board, size, side):
            return side
        side = opponent(side)


def test_shortest_path_counts_the_stones_still_needed():
    size = 7
    assert shortest_path(empty_board(size), size, 'red') == (size, set(range(size * size)))
    board = board_with(size, red=column(size, 3, range(5)), blue=[5 * size + 2])
    needed, cells = shortest_path(board, size, 'red')
    assert needed == 2 and cells == {5 * size + 3, 6 * size + 2, 6 * size + 3}
    walled = board_with(size, blue=row_cells(size, 3))
    assert shortest_path(walled, size, 'red') == (ai.BLOCKED, set())
    assert shortest_path(walled, size, 'blue')[0] == 0


@pytest.mark.parametrize('size', SIZES)
@pytest.mark.parametrize('difficulty', LEVELS)
def test_every_level_plays_an_empty_cell_on_every_board_size(size, difficulty):
    rng = Random(1)
    board = empty_board(size)
    for side in ['red', 'blue'] * 6:
        cell = choose_move(board, size, side, difficulty, rng)
        assert board[cell] == EMPTY
        board = place(board, size, side, cell)


@pytest.mark.parametrize('difficulty', LEVELS)
def test_every_level_finishes_a_connection_that_is_one_stone_away(difficulty):
    size = 7
    # Two cells finish Blue's row: the last one in it, and the edge cell above that.
    board = board_with(size, blue=row_cells(size, 3, range(size - 1)), red=column(size, 1, range(3)))
    for seed in range(5):
        cell = choose_move(board, size, 'blue', difficulty, Random(seed))
        assert cell in {3 * size + size - 1, 2 * size + size - 1}
        assert winning_path(place(board, size, 'blue', cell), size, 'blue')


@pytest.mark.parametrize('difficulty', ['normal', 'hard'])
def test_normal_and_hard_always_stop_a_connection_that_is_one_stone_away(difficulty):
    size = 7
    # Red needs only the last cell of the column. Blue is far from connecting.
    board = board_with(size, red=column(size, 3, range(size - 1)), blue=[0, 1, 2, 4, 5, 6 * size + 2])
    for seed in range(5):
        assert choose_move(board, size, 'blue', difficulty, Random(seed)) == 6 * size + 3


def test_easy_sometimes_misses_a_block_and_plays_on_a_shortest_path():
    size = 7
    board = board_with(size, red=column(size, 3, range(size - 1)), blue=[0, 1, 2, 4, 5, 6 * size + 2])
    cells = {choose_move(board, size, 'blue', 'easy', Random(seed)) for seed in range(40)}
    assert 6 * size + 3 in cells and len(cells) > 1
    on_a_path = shortest_path(board, size, 'blue')[1] | shortest_path(board, size, 'red')[1]
    assert cells <= on_a_path


def test_hard_keeps_a_bridge_when_one_of_its_two_cells_is_taken():
    size = 5
    # Blue's stones are joined to each other and to both edges by pairs of empty cells: every pair is safe
    # as long as Blue answers in the same pair. Red has just taken one cell of the middle pair.
    first, second = 2 * size + 1, 1 * size + 3
    between = {1 * size + 2, 2 * size + 2}
    assert between == set(ai.neighbors(size)[first]) & set(ai.neighbors(size)[second])
    board = board_with(size, blue=[first, second], red=[1 * size + 2, 4 * size + 4])
    for seed in range(5):
        assert choose_move(board, size, 'blue', 'hard', Random(seed)) == 2 * size + 2


def test_two_distance_prefers_a_block_from_a_distance_over_one_next_to_the_stone():
    size = 9
    # Red has run down the middle from the top. The cell straight in front can be walked around; the
    # cell one further back, between both ways forward, costs Red a move.
    board = board_with(size, red=column(size, 4, range(4)), blue=[size * 8, size * 8 + 1, size * 7])
    head = 3 * size + 4
    in_front = {head + size, head + size - 1}
    for seed in range(5):
        assert choose_move(board, size, 'blue', 'hard', Random(seed)) not in in_front


def test_a_full_board_has_no_move():
    assert choose_move([1, 2, 1, 2], 2, 'red', 'hard') is None


def minimax_choices(board, size, side):
    """The cells hard may play: its own search written without pruning, as a reference."""

    def value(turn, depth):
        needed, _ = shortest_path(board, size, turn)
        if needed == 1:
            return ai.WON + depth
        other_needed, other_path = shortest_path(board, size, opponent(turn))
        score, cells = ai._evaluate(board, size, turn)
        if depth == 0:
            return score
        if other_needed == 1:
            if len(other_path) > 1:
                return -ai.WON - depth
            cells = list(other_path)
        replies = []
        for cell in cells[: ai.INNER_BRANCHES]:
            board[cell] = STONES[turn]
            replies.append(-value(opponent(turn), depth - 1))
            board[cell] = EMPTY
        return max(replies)

    board = list(board)
    scored = []
    for cell in ai._evaluate(board, size, side)[1][: ai.ROOT_BRANCHES]:
        board[cell] = STONES[side]
        scored.append((-value(opponent(side), ai.HARD_DEPTH - 1), cell))
        board[cell] = EMPTY
    best = max(score for score, _ in scored)
    return {cell for score, cell in scored if score == best}


@pytest.mark.parametrize('size,seed,plies', [(7, 1, 5), (7, 2, 9), (7, 3, 13), (9, 4, 7), (9, 5, 11), (9, 6, 17)])
def test_hard_plays_what_a_search_without_pruning_would_play(size, seed, plies):
    rng = Random(seed)
    board, side = empty_board(size), 'red'
    for _ in range(plies):
        board = place(board, size, side, choose_move(board, size, side, 'normal', rng))
        side = opponent(side)
    assert not winning_path(board, size, 'red') and not winning_path(board, size, 'blue')
    # Positions with a stone-away win or threat are answered before the search starts.
    assert min(shortest_path(board, size, 'red')[0], shortest_path(board, size, 'blue')[0]) > 1
    expected = minimax_choices(board, size, side)
    chosen = {choose_move(board, size, side, 'hard', Random(attempt)) for attempt in range(12)}
    assert chosen <= expected


def test_each_level_beats_the_one_below_it():
    # Seeded games in which the weaker level has the advantage of moving first.
    assert sum(play(9, 'easy', 'normal', seed) == 'blue' for seed in range(6)) == 6
    assert sum(play(9, 'normal', 'hard', seed) == 'blue' for seed in range(6)) >= 4


@pytest.mark.parametrize('size', SIZES)
def test_hard_tries_a_bounded_number_of_positions(size):
    board = place(empty_board(size), size, 'red', (size // 2) * size + size // 2)
    with patch.object(ai, '_evaluate', wraps=ai._evaluate) as evaluate:
        assert board[choose_move(board, size, 'blue', 'hard', Random(0))] == EMPTY
    root, inner = ai.ROOT_BRANCHES, ai.INNER_BRANCHES
    assert ai.HARD_DEPTH == 3 and evaluate.call_count <= 1 + root + root * inner + root * inner * inner == 517
