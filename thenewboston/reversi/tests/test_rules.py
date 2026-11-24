from random import Random

import pytest

from thenewboston.reversi.rules import (
    PIECES,
    apply_move,
    count_disks,
    initial_board,
    leader,
    legal_moves,
    next_side,
    opponent,
    to_bits,
    to_board,
)

# Black to move. Either black move leaves white without a reply.
PASS_BOARD = ['.wb.....', '........', '........', '........', '........', '........', '........', '......wb']


def full_board(black_rows):
    """A board with one empty corner. Black fills it, flips one disk, and ends the game with `black_rows` rows."""
    return ['.wbbbbbb'] + ['bbbbbbbb'] * (black_rows - 1) + ['wwwwwwww'] * (8 - black_rows)


def reference_flips(board, side, row, column):
    """A deliberately plain implementation to check the bitboard rules against."""
    own, other = PIECES[side], PIECES[opponent(side)]
    if board[row][column] != '.':
        return []
    flipped = []
    for row_step in (-1, 0, 1):
        for column_step in (-1, 0, 1):
            if not row_step and not column_step:
                continue
            line = []
            r, c = row + row_step, column + column_step
            while 0 <= r < 8 and 0 <= c < 8 and board[r][c] == other:
                line.append([r, c])
                r, c = r + row_step, c + column_step
            if line and 0 <= r < 8 and 0 <= c < 8 and board[r][c] == own:
                flipped += line
    return sorted(flipped)


def test_opening_position_and_first_moves():
    board = initial_board()
    assert count_disks(board) == {'black': 2, 'white': 2}
    assert legal_moves(board, 'black') == [(2, 3), (3, 2), (4, 5), (5, 4)]
    assert legal_moves(board, 'white') == [(2, 4), (3, 5), (4, 2), (5, 3)]
    board, flipped = apply_move(board, 'black', 2, 3)
    assert flipped == [[3, 3]]
    assert board[2:5] == ['...b....', '...bb...', '...bw...']
    assert next_side(board, 'black') == 'white'


def test_board_round_trips_through_bits():
    board = ['bw......', '........', '..b.....', '...wb...', '...bw...', '........', '........', '.......w']
    assert to_board(*to_bits(board)) == board


def test_one_move_flips_every_outflanked_line():
    board = ['b.b.b...', '.www....', 'bw.wb...', '.www....', 'b.b.b...', '........', '........', '........']
    board, flipped = apply_move(board, 'black', 2, 2)
    assert flipped == [[1, 1], [1, 2], [1, 3], [2, 1], [2, 3], [3, 1], [3, 2], [3, 3]]
    assert count_disks(board) == {'black': 17, 'white': 0}


def test_lines_do_not_wrap_around_the_board_edges():
    # The white disk ends one row and the black disk starts the next: they are not neighbours.
    board = ['.......w', 'b.......', '........', '........', '........', '........', '........', '........']
    assert legal_moves(board, 'black') == []
    assert legal_moves(board, 'white') == []
    board = ['......wb', '........', '........', '........', '........', '........', '........', 'bw......']
    assert legal_moves(board, 'black') == [(0, 5), (7, 2)]


@pytest.mark.parametrize(
    'row,column,message',
    [
        (3, 3, 'already taken'),
        (0, 0, 'outflank'),
        (8, 0, 'inside the board'),
        (0, -1, 'inside the board'),
        ('2', 3, 'inside the board'),
        (True, 3, 'inside the board'),
    ],
)
def test_illegal_moves_are_rejected(row, column, message):
    with pytest.raises(ValueError, match=message):
        apply_move(initial_board(), 'black', row, column)


@pytest.mark.parametrize(
    'board', [None, [], ['........'] * 7, ['.......'] * 8, ['.......x'] + ['........'] * 7, [[0] * 8] * 8]
)
def test_malformed_boards_are_rejected(board):
    with pytest.raises(ValueError, match='not a valid Reversi position'):
        legal_moves(board, 'black')


def test_a_player_without_a_move_passes_and_the_game_ends_when_nobody_can_move():
    board, _ = apply_move(PASS_BOARD, 'black', 0, 0)
    assert legal_moves(board, 'white') == []
    assert next_side(board, 'black') == 'black'
    board, flipped = apply_move(board, 'black', 7, 5)
    assert flipped == [[7, 6]]
    assert next_side(board, 'black') is None
    assert leader(board) == 'black'


@pytest.mark.parametrize(
    'black_rows,winner,counts', [(5, 'black', (40, 24)), (4, None, (32, 32)), (3, 'white', (24, 40))]
)
def test_final_count_decides_the_winner(black_rows, winner, counts):
    board, _ = apply_move(full_board(black_rows), 'black', 0, 0)
    assert next_side(board, 'black') is None
    assert leader(board) == winner
    assert count_disks(board) == {'black': counts[0], 'white': counts[1]}


def test_random_games_match_the_reference_rules():
    rng = Random(20261123)
    for _ in range(40):
        board, side, turns = initial_board(), 'black', 0
        while side:
            expected = [
                (row, column) for row in range(8) for column in range(8) if reference_flips(board, side, row, column)
            ]
            assert legal_moves(board, side) == expected
            row, column = rng.choice(expected)
            expected_flips = reference_flips(board, side, row, column)
            board, flipped = apply_move(board, side, row, column)
            assert flipped == expected_flips
            side = next_side(board, side)
            turns += 1
        assert turns <= 60
        assert not legal_moves(board, 'black') and not legal_moves(board, 'white')
