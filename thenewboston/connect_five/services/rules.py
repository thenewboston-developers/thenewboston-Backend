from copy import deepcopy

from rest_framework.exceptions import ValidationError

from ..constants import BOARD_SIZE, CONNECT_LENGTH
from ..enums import MoveType


def apply_move(*, board_state, move_type, player_value, x, y):
    board = deepcopy(board_state)
    placed_positions = []
    removed_positions = []

    def in_bounds(x_pos, y_pos):
        return 0 <= x_pos < BOARD_SIZE and 0 <= y_pos < BOARD_SIZE

    def is_empty(x_pos, y_pos):
        return board[y_pos][x_pos] == 0

    def place(x_pos, y_pos):
        board[y_pos][x_pos] = player_value
        placed_positions.append((x_pos, y_pos))

    def remove(x_pos, y_pos):
        board[y_pos][x_pos] = 0
        removed_positions.append((x_pos, y_pos))

    if move_type == MoveType.SINGLE:
        if not in_bounds(x, y) or not is_empty(x, y):
            raise ValidationError({'detail': 'Invalid single placement.'})
        place(x, y)
    elif move_type == MoveType.H2:
        positions = [(x, y), (x + 1, y)]
        if not all(in_bounds(x_pos, y_pos) for x_pos, y_pos in positions):
            raise ValidationError({'detail': 'Horizontal placement out of bounds.'})
        if not all(is_empty(x_pos, y_pos) for x_pos, y_pos in positions):
            raise ValidationError({'detail': 'Horizontal placement overlaps existing pieces.'})
        for x_pos, y_pos in positions:
            place(x_pos, y_pos)
    elif move_type == MoveType.V2:
        positions = [(x, y), (x, y + 1)]
        if not all(in_bounds(x_pos, y_pos) for x_pos, y_pos in positions):
            raise ValidationError({'detail': 'Vertical placement out of bounds.'})
        if not all(is_empty(x_pos, y_pos) for x_pos, y_pos in positions):
            raise ValidationError({'detail': 'Vertical placement overlaps existing pieces.'})
        for x_pos, y_pos in positions:
            place(x_pos, y_pos)
    elif move_type == MoveType.CROSS4:
        positions = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
        if not all(in_bounds(x_pos, y_pos) for x_pos, y_pos in positions):
            raise ValidationError({'detail': 'Cross placement out of bounds.'})
        if not all(is_empty(x_pos, y_pos) for x_pos, y_pos in positions):
            raise ValidationError({'detail': 'Cross placement overlaps existing pieces.'})
        for x_pos, y_pos in positions:
            place(x_pos, y_pos)
    elif move_type == MoveType.BOMB:
        if not in_bounds(x, y):
            raise ValidationError({'detail': 'Bomb target out of bounds.'})
        target_value = board[y][x]
        if target_value == 0 or target_value == player_value:
            raise ValidationError({'detail': 'Bomb target must be an opponent piece.'})
        remove(x, y)
    else:
        raise ValidationError({'detail': 'Unknown move type.'})

    return board, placed_positions, removed_positions


def check_win(*, board_state, player_value, positions):
    def count_direction(x_start, y_start, dx, dy):
        count = 1
        step = 1
        while True:
            x_pos = x_start + dx * step
            y_pos = y_start + dy * step
            if not (0 <= x_pos < BOARD_SIZE and 0 <= y_pos < BOARD_SIZE):
                break
            if board_state[y_pos][x_pos] != player_value:
                break
            count += 1
            step += 1
        step = 1
        while True:
            x_pos = x_start - dx * step
            y_pos = y_start - dy * step
            if not (0 <= x_pos < BOARD_SIZE and 0 <= y_pos < BOARD_SIZE):
                break
            if board_state[y_pos][x_pos] != player_value:
                break
            count += 1
            step += 1
        return count

    for x_pos, y_pos in positions:
        if count_direction(x_pos, y_pos, 1, 0) >= CONNECT_LENGTH:
            return True
        if count_direction(x_pos, y_pos, 0, 1) >= CONNECT_LENGTH:
            return True
        if count_direction(x_pos, y_pos, 1, 1) >= CONNECT_LENGTH:
            return True
        if count_direction(x_pos, y_pos, 1, -1) >= CONNECT_LENGTH:
            return True

    return False


def is_draw(board_state):
    return all(cell != 0 for row in board_state for cell in row)
