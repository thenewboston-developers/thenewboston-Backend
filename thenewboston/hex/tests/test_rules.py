from random import Random

import pytest

from thenewboston.hex.rules import (
    BLUE,
    EMPTY,
    RED,
    SIZES,
    edges,
    empty_board,
    mirror,
    neighbors,
    opponent,
    place,
    swap,
    winning_path,
)


def board_with(size, red=(), blue=()):
    board = empty_board(size)
    for cell in red:
        board[cell] = RED
    for cell in blue:
        board[cell] = BLUE
    return board


def column(size, index, rows=None):
    return [row * size + index for row in (range(size) if rows is None else rows)]


def row_cells(size, index, columns=None):
    return [index * size + col for col in (range(size) if columns is None else columns)]


@pytest.mark.parametrize('size', SIZES)
def test_board_is_a_rhombus_of_six_sided_cells(size):
    table = neighbors(size)
    assert len(empty_board(size)) == len(table) == size * size
    # The two sharp corners touch two cells, the two blunt corners three, edges four and the inside six.
    assert sorted(len(table[corner]) for corner in (0, size - 1, size * (size - 1), size * size - 1)) == [2, 2, 3, 3]
    assert len(table[1]) == 4 and len(table[size + 1]) == 6
    assert all(cell in table[other] for cell, around in enumerate(table) for other in around)
    assert opponent('red') == 'blue' and opponent('blue') == 'red'


def test_cells_touch_along_the_short_diagonal_only():
    size = 5
    middle = 2 * size + 2
    assert set(neighbors(size)[middle]) == {
        middle - size,
        middle - size + 1,
        middle - 1,
        middle + 1,
        middle + size - 1,
        middle + size,
    }
    # Down-left joins, down-right does not.
    assert winning_path(board_with(size, red=[4, 8, 12, 16, 20]), size, 'red') == [4, 8, 12, 16, 20]
    assert winning_path(board_with(size, red=[0, 6, 12, 18, 24]), size, 'red') is None


@pytest.mark.parametrize('size', SIZES)
def test_each_side_wins_only_by_joining_its_own_edges(size):
    red = board_with(size, red=column(size, 2))
    assert winning_path(red, size, 'red') == column(size, 2)
    assert winning_path(red, size, 'blue') is None
    blue = board_with(size, blue=row_cells(size, 3))
    assert winning_path(blue, size, 'blue') == row_cells(size, 3)
    assert winning_path(blue, size, 'red') is None
    # A full row of red stones and a full column of blue stones connect nothing.
    assert winning_path(board_with(size, red=row_cells(size, 3)), size, 'red') is None
    assert winning_path(board_with(size, blue=column(size, 2)), size, 'blue') is None
    assert winning_path(board_with(size, red=column(size, 2, range(size - 1))), size, 'red') is None


def test_winning_path_is_the_shortest_chain_without_side_branches():
    size = 7
    chain = column(size, 3)
    board = board_with(size, red=[*chain, 2 * size + 4, 2 * size + 5, 4 * size + 2])
    assert winning_path(board, size, 'red') == chain


@pytest.mark.parametrize('size', SIZES)
def test_a_full_board_always_has_exactly_one_winner(size):
    rng = Random(size)
    for _ in range(200):
        board = [rng.choice((RED, BLUE)) for _ in range(size * size)]
        winners = [side for side in ('red', 'blue') if winning_path(board, size, side)]
        assert len(winners) == 1


def test_place_needs_an_empty_cell_on_the_board_and_leaves_the_original_alone():
    size = 7
    board = empty_board(size)
    updated = place(board, size, 'red', 10)
    assert updated[10] == RED and board[10] == EMPTY
    assert place(updated, size, 'blue', 11)[11] == BLUE
    for cell in (10, -1, size * size, '10', 10.0, None, True):
        with pytest.raises(ValueError):
            place(updated, size, 'blue', cell)


@pytest.mark.parametrize('size', SIZES)
def test_mirror_turns_reds_edges_into_blues(size):
    red_edges, blue_edges = edges(size, 'red'), edges(size, 'blue')
    for red_edge, blue_edge in zip(red_edges, blue_edges):
        assert sorted(mirror(size, cell) for cell in red_edge) == list(blue_edge)
    assert all(mirror(size, mirror(size, cell)) == cell for cell in range(size * size))
    # Mirroring keeps cells next to each other, so a red chain becomes a blue chain.
    table = neighbors(size)
    assert all(mirror(size, other) in table[mirror(size, cell)] for cell in range(size * size) for other in table[cell])


def test_swap_moves_the_opening_stone_to_its_mirror_cell_as_blue():
    size = 11
    origin = 2 * size + 7
    board, moved_from, moved_to = swap(place(empty_board(size), size, 'red', origin), size)
    assert (moved_from, moved_to) == (origin, 7 * size + 2)
    assert board.count(BLUE) == 1 and board.count(RED) == 0 and board[moved_to] == BLUE
    # A stone on the long diagonal stays where it is.
    centre = 5 * size + 5
    assert swap(board_with(size, red=[centre]), size)[0] == board_with(size, blue=[centre])


@pytest.mark.parametrize('red,blue', [((), ()), ((1, 2), ()), ((1,), (2,)), ((), (1,))])
def test_swap_is_only_possible_straight_after_the_first_stone(red, blue):
    with pytest.raises(ValueError):
        swap(board_with(7, red=red, blue=blue), 7)
