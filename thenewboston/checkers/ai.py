"""Bounded alpha-beta search over the same complete legal turns as human play."""

from random import choice

from .rules import apply_legal_move, legal_moves, opponent, piece_side


def _evaluate(board, side):
    score = 0
    for square, piece in enumerate(board):
        if not piece:
            continue
        row, column = divmod(square, 8)
        advancement = 7 - row if piece > 0 else row
        value = 175 if abs(piece) == 2 else 100 + advancement * 4
        value += 3 if 2 <= column <= 5 else 0
        score += value if piece_side(piece) == side else -value
    return score


def choose_move(board, side, difficulty):
    moves = legal_moves(board, side)
    if not moves:
        return None
    if difficulty == 'easy':
        return choice(moves)
    depth = 3 if difficulty == 'normal' else 5
    budget = [12000]

    def search(position, turn, remaining, alpha, beta):
        budget[0] -= 1
        available = legal_moves(position, turn)
        if not available:
            return -100000 - remaining if turn == side else 100000 + remaining
        if remaining == 0 or budget[0] <= 0:
            return _evaluate(position, side)
        maximizing = turn == side
        value = float('-inf') if maximizing else float('inf')
        for path in available:
            next_board, _ = apply_legal_move(position, path)
            score = search(next_board, opponent(turn), remaining - 1, alpha, beta)
            value = max(value, score) if maximizing else min(value, score)
            if maximizing:
                alpha = max(alpha, value)
            else:
                beta = min(beta, value)
            if beta <= alpha or budget[0] <= 0:
                break
        return value

    best_score = float('-inf')
    best_moves = []
    for path in moves:
        updated, _ = apply_legal_move(board, path)
        score = search(updated, opponent(side), depth - 1, float('-inf'), float('inf'))
        if score > best_score:
            best_score, best_moves = score, [path]
        elif score == best_score:
            best_moves.append(path)
    return choice(best_moves)
