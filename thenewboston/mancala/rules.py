"""Pure Mancala (Kalah) rules: six pits a side, four stones a pit.

The board is a list of 14 counts in sowing order. Indexes 0-5 are the host's
pits and 6 is the host's store; 7-12 are the guest's pits and 13 is the guest's
store. A player names one of their own pits 0-5, also in sowing order, so pit 5
is always the one next to that player's store.
"""

PITS = 6
STONES_PER_PIT = 4
SIZE = 2 * PITS + 2
STORE = {'host': PITS, 'guest': SIZE - 1}
TOTAL_STONES = 2 * PITS * STONES_PER_PIT


def opponent(side):
    return 'guest' if side == 'host' else 'host'


def initial_board():
    row = [STONES_PER_PIT] * PITS
    return [*row, 0, *row, 0]


def pit_index(side, pit):
    return pit if side == 'host' else pit + PITS + 1


def side_indexes(side):
    start = pit_index(side, 0)
    return range(start, start + PITS)


def legal_pits(board, side):
    return [pit for pit in range(PITS) if board[pit_index(side, pit)]]


def sow(board, side, pit):
    """Play one pit. Returns the new board and a description of what happened."""
    if type(pit) is not int or not 0 <= pit < PITS:
        raise ValueError('Choose one of your six pits.')
    board = list(board)
    index = pit_index(side, pit)
    stones = board[index]
    if not stones:
        raise ValueError('Choose a pit that has stones in it.')
    board[index] = 0
    skipped = STORE[opponent(side)]
    remaining = stones
    while remaining:
        index = (index + 1) % SIZE
        if index == skipped:
            continue
        board[index] += 1
        remaining -= 1

    captured = 0
    if index in side_indexes(side) and board[index] == 1:
        # Opposite pits always add up to 12: 0 faces 12, 5 faces 7.
        opposite = 2 * PITS - index
        if board[opposite]:
            captured = board[opposite] + 1
            board[opposite] = board[index] = 0
            board[STORE[side]] += captured

    swept = None
    if any(not any(board[i] for i in side_indexes(player)) for player in ('host', 'guest')):
        # One row is empty: the stones left in the other row go to that row's owner.
        swept = {}
        for player in ('host', 'guest'):
            swept[player] = sum(board[i] for i in side_indexes(player))
            for i in side_indexes(player):
                board[i] = 0
            board[STORE[player]] += swept[player]

    move = {
        'side': side,
        'pit': pit,
        'stones': stones,
        'last': index,
        'captured': captured,
        'extra_turn': swept is None and index == STORE[side],
        'swept': swept,
    }
    return board, move


def is_finished(board):
    return not any(board[i] for side in ('host', 'guest') for i in side_indexes(side))


def leader(board):
    """The side with more stones in its store, or None when the stores are level."""
    host, guest = board[STORE['host']], board[STORE['guest']]
    if host == guest:
        return None
    return 'host' if host > guest else 'guest'
