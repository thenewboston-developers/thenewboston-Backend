"""Pure Reversi (Othello) rules.

A stored board is eight strings of eight characters: '.' is empty, 'b' is a
black disk and 'w' is a white disk. Row 0 is the top row. Black moves first.

Internally each color is a 64-bit integer with one bit per square
(bit = row * 8 + column), which keeps the computer's search cheap.
"""

BOARD_SIZE = 8
SIDES = ('black', 'white')
FULL = 0xFFFFFFFFFFFFFFFF
NOT_FIRST_COLUMN = 0xFEFEFEFEFEFEFEFE
NOT_LAST_COLUMN = 0x7F7F7F7F7F7F7F7F
# (shift, mask that removes squares which wrapped around a board edge)
SHIFTS_UP = ((1, NOT_FIRST_COLUMN), (8, FULL), (9, NOT_FIRST_COLUMN), (7, NOT_LAST_COLUMN))
SHIFTS_DOWN = ((1, NOT_LAST_COLUMN), (8, FULL), (9, NOT_LAST_COLUMN), (7, NOT_FIRST_COLUMN))
PIECES = {'black': 'b', 'white': 'w'}


def opponent(side):
    return 'white' if side == 'black' else 'black'


def initial_board():
    return ['........', '........', '........', '...wb...', '...bw...', '........', '........', '........']


def to_bits(board):
    """Return (black, white) integers for a stored board."""
    if (
        not isinstance(board, list)
        or len(board) != BOARD_SIZE
        or any(not isinstance(row, str) or len(row) != BOARD_SIZE or set(row) - set('.bw') for row in board)
    ):
        raise ValueError('The board is not a valid Reversi position.')
    black = white = 0
    for index, piece in enumerate(''.join(board)):
        if piece == 'b':
            black |= 1 << index
        elif piece == 'w':
            white |= 1 << index
    return black, white


def to_board(black, white):
    squares = ['b' if black >> index & 1 else 'w' if white >> index & 1 else '.' for index in range(64)]
    return [''.join(squares[row * BOARD_SIZE : (row + 1) * BOARD_SIZE]) for row in range(BOARD_SIZE)]


def moves_mask(own, other):
    """Every empty square where `own` would flip at least one disk."""
    empty = ~(own | other) & FULL
    moves = 0
    for shift, mask in SHIFTS_UP:
        line = (own << shift) & mask & other
        for _ in range(BOARD_SIZE - 3):
            line |= (line << shift) & mask & other
        moves |= (line << shift) & mask & empty
    for shift, mask in SHIFTS_DOWN:
        line = (own >> shift) & mask & other
        for _ in range(BOARD_SIZE - 3):
            line |= (line >> shift) & mask & other
        moves |= (line >> shift) & mask & empty
    return moves


def flips_mask(own, other, move):
    """Disks of `other` that turn over when `own` plays the single-bit `move`."""
    flipped = 0
    for shift, mask in SHIFTS_UP:
        line = 0
        cursor = (move << shift) & mask
        while cursor & other:
            line |= cursor
            cursor = (cursor << shift) & mask
        if cursor & own:
            flipped |= line
    for shift, mask in SHIFTS_DOWN:
        line = 0
        cursor = (move >> shift) & mask
        while cursor & other:
            line |= cursor
            cursor = (cursor >> shift) & mask
        if cursor & own:
            flipped |= line
    return flipped


def squares(mask):
    """Sorted (row, column) pairs for every set bit."""
    result = []
    while mask:
        bit = mask & -mask
        result.append(divmod(bit.bit_length() - 1, BOARD_SIZE))
        mask ^= bit
    return result


def _own_and_other(board, side):
    if side not in SIDES:
        raise ValueError('Unknown side.')
    black, white = to_bits(board)
    return (black, white) if side == 'black' else (white, black)


def legal_moves(board, side):
    return squares(moves_mask(*_own_and_other(board, side)))


def apply_move(board, side, row, column):
    """Return (new board, flipped squares). Raises ValueError for an illegal move."""
    if type(row) is not int or type(column) is not int or not 0 <= row < BOARD_SIZE or not 0 <= column < BOARD_SIZE:
        raise ValueError('Choose a square inside the board.')
    own, other = _own_and_other(board, side)
    move = 1 << (row * BOARD_SIZE + column)
    if move & (own | other):
        raise ValueError('That square is already taken.')
    flipped = flips_mask(own, other, move)
    if not flipped:
        raise ValueError('A move must outflank at least one opposing disk.')
    own |= move | flipped
    other &= ~flipped
    black, white = (own, other) if side == 'black' else (other, own)
    return to_board(black, white), [list(square) for square in squares(flipped)]


def count_disks(board):
    black, white = to_bits(board)
    return {'black': black.bit_count(), 'white': white.bit_count()}


def next_side(board, moved_side):
    """Who moves after `moved_side`: the opponent, the same side after a forced pass, or None when the game is over."""
    own, other = _own_and_other(board, moved_side)
    if moves_mask(other, own):
        return opponent(moved_side)
    if moves_mask(own, other):
        return moved_side
    return None


def leader(board):
    """The side with more disks, or None for a tie."""
    counts = count_disks(board)
    if counts['black'] == counts['white']:
        return None
    return 'black' if counts['black'] > counts['white'] else 'white'
