"""Bounded tactical computer play using the same move rules as human games."""

from random import SystemRandom

from rest_framework.exceptions import ValidationError

from .rules import apply_move, check_win
from ..constants import BOARD_SIZE, CONNECT_LENGTH
from ..enums import MoveType

INVENTORY_FIELDS = {MoveType.H2: 'inventory_h2', MoveType.V2: 'inventory_v2', MoveType.BOMB: 'inventory_bomb'}


def legal_moves(board, player_value, inventory):
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            types = [MoveType.SINGLE] if board[y][x] == 0 else []
            types.extend(move for move, field in INVENTORY_FIELDS.items() if inventory.get(field, 0) > 0)
            for move_type in types:
                move = {'move_type': move_type, 'x': x, 'y': y}
                try:
                    result, placed, removed = apply_move(board_state=board, player_value=player_value, **move)
                except ValidationError:
                    continue
                yield move, result, placed, removed


def _windows():
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                end_x, end_y = x + dx * (CONNECT_LENGTH - 1), y + dy * (CONNECT_LENGTH - 1)
                if 0 <= end_x < BOARD_SIZE and 0 <= end_y < BOARD_SIZE:
                    yield [(x + step * dx, y + step * dy) for step in range(CONNECT_LENGTH)]


WINDOWS = tuple(_windows())
WEIGHTS = (0, 1, 10, 100, 2500, 1000000)


def _position_score(board):
    score = 0
    for window in WINDOWS:
        counts = [0, 0, 0]
        for x, y in window:
            counts[board[y][x]] += 1
        if not counts[1]:
            score += WEIGHTS[counts[2]]
        if not counts[2]:
            score -= WEIGHTS[counts[1]] * 1.1
    return score


def _winning_moves(board, player_value, inventory):
    return [
        move
        for move, result, placed, _ in legal_moves(board, player_value, inventory)
        if placed and check_win(board_state=result, player_value=player_value, positions=placed)
    ]


def choose_move(board, computer_inventory, human_inventory, difficulty='normal', rng=None):
    rng = rng or SystemRandom()
    candidates = list(legal_moves(board, 2, computer_inventory))
    if not candidates:
        raise ValueError('No legal computer move is available.')
    if difficulty == 'easy':
        return rng.choice(candidates)[0]
    wins = [
        candidate
        for candidate in candidates
        if candidate[2] and check_win(board_state=candidate[1], player_value=2, positions=candidate[2])
    ]
    if wins:
        return rng.choice(wins)[0]
    threats = _winning_moves(board, 1, human_inventory)
    ranked = []
    for move, result, _, _ in candidates:
        unblocked = 0
        for threat in threats:
            try:
                reply, placed, _ = apply_move(board_state=result, player_value=1, **threat)
            except ValidationError:
                continue
            if check_win(board_state=reply, player_value=1, positions=placed):
                unblocked += 1
        # Block all immediate wins before optimizing position; conserve specials on ties.
        score = _position_score(result) - (1 if move['move_type'] != MoveType.SINGLE else 0)
        ranked.append((unblocked, score, move, result))
    safest = min(item[0] for item in ranked)
    ranked = [item for item in ranked if item[0] == safest]
    ranked.sort(key=lambda item: item[1], reverse=True)
    if difficulty == 'hard':
        # Bounded one-turn lookahead: favor positions with multiple future winning squares.
        for index, (risk, score, move, result) in enumerate(ranked[:8]):
            inventory = dict(computer_inventory)
            if field := INVENTORY_FIELDS.get(move['move_type']):
                inventory[field] -= 1
            future = _winning_moves(result, 2, inventory)
            winning_squares = {(candidate['x'], candidate['y']) for candidate in future}
            ranked[index] = (risk, score + min(len(winning_squares), 4) * 10000, move, result)
    best = max(item[1] for item in ranked)
    return rng.choice([item[2] for item in ranked if item[1] == best])
