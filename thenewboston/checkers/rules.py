"""English/American checkers, with complete turns represented as square paths.

White starts at the bottom and moves up. Men capture forward only; kings move
and capture in both directions. Captures are mandatory, every jump in a chain
must be completed, and reaching the king row ends the turn immediately.
"""


def initial_board():
    return [(-1 if row < 3 else 1 if row > 4 else 0) if (row + col) % 2 else 0 for row in range(8) for col in range(8)]


def opponent(side):
    return 'black' if side == 'white' else 'white'


def piece_side(piece):
    return ('white' if piece > 0 else 'black') if piece else None


def _directions(piece):
    return (-1, 1) if abs(piece) == 2 else (-1,) if piece > 0 else (1,)


def _crowned(piece, row):
    return abs(piece) == 1 and row == (0 if piece > 0 else 7)


def _captures(board, square, path):
    piece = board[square]
    row, col = divmod(square, 8)
    paths = []
    for dr in _directions(piece):
        for dc in (-1, 1):
            target_row, target_col = row + 2 * dr, col + 2 * dc
            if not (0 <= target_row < 8 and 0 <= target_col < 8):
                continue
            target = target_row * 8 + target_col
            middle = (row + dr) * 8 + col + dc
            if board[target] or board[middle] * piece >= 0:
                continue
            updated = board.copy()
            updated[square] = updated[middle] = 0
            updated[target] = piece
            next_path = [*path, target]
            # A newly crowned man cannot continue jumping as a king this turn.
            continuations = [] if _crowned(piece, target_row) else _captures(updated, target, next_path)
            paths.extend(continuations or [next_path])
    return paths


def legal_moves(board, side):
    captures = []
    squares = [square for square, piece in enumerate(board) if piece_side(piece) == side]
    for square in squares:
        captures.extend(_captures(board, square, [square]))
    if captures:
        return captures
    moves = []
    for square in squares:
        row, col = divmod(square, 8)
        for dr in _directions(board[square]):
            for dc in (-1, 1):
                target_row, target_col = row + dr, col + dc
                if 0 <= target_row < 8 and 0 <= target_col < 8 and not board[target_row * 8 + target_col]:
                    moves.append([square, target_row * 8 + target_col])
    return moves


def apply_legal_move(board, path):
    """Apply an already validated full path; also used by the computer search."""
    updated = board.copy()
    piece = updated[path[0]]
    captured = []
    for origin, target in zip(path, path[1:]):
        row, col = divmod(origin, 8)
        target_row, target_col = divmod(target, 8)
        updated[origin] = 0
        if abs(target_row - row) == 2:
            middle = ((row + target_row) // 2) * 8 + (col + target_col) // 2
            captured.append(middle)
            updated[middle] = 0
        updated[target] = piece
    if _crowned(piece, path[-1] // 8):
        updated[path[-1]] = 2 * piece
    return updated, captured


def apply_move(board, side, path):
    if (
        not isinstance(path, list)
        or any(type(square) is not int for square in path)
        or path not in legal_moves(board, side)
    ):
        raise ValueError('Choose a legal move and complete every required jump.')
    return apply_legal_move(board, path)


def position_key(board, side):
    return side + ':' + ','.join(map(str, board))
