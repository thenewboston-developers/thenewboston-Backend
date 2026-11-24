"""Authoritative Checkers transitions with locked, atomic stake settlement.

Existing-match callers hold its row lock within a transaction. Every wallet
change and its audit ledger entry commit with the corresponding match state.
"""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from thenewboston.currencies.models import Currency
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.wallets.models import Wallet

from .models import CheckersEvent, CheckersLedgerEntry, CheckersMatch
from .rules import apply_move, initial_board, legal_moves, opponent, position_key

UNFINISHED = ['pending', 'active']
logger = logging.getLogger(__name__)


class StateConflict(APIException):
    status_code = 409
    default_detail = 'The match changed. Refresh it before trying again.'


def player_side(match, user_id):
    if user_id == match.white_id:
        return 'white'
    if user_id is not None and user_id == match.black_id:
        return 'black'
    return None


def _transfer(match, user_id, amount, action):
    if not amount:
        return
    wallet = Wallet.objects.select_for_update().filter(currency_id=match.currency_id, owner_id=user_id).first()
    if wallet is None:
        raise ValidationError('A TNB wallet is required for a staked match.')
    if wallet.balance + amount < 0:
        raise ValidationError('Insufficient TNB balance for this stake.')
    CheckersLedgerEntry.objects.create(match=match, wallet=wallet, amount=amount, action=action)
    wallet.change_balance(amount, should_stream=True)


def _record(match, event_type, payload=None, *, initial=False):
    if not initial:
        match.version += 1
    match.save()
    CheckersEvent.objects.create(match=match, version=match.version, event_type=event_type, payload=payload or {})


def _start_game(match):
    match.status = 'active'
    match.board = initial_board()
    match.active_side = 'white'
    match.turn_started_at = timezone.now()
    match.position_counts = {position_key(match.board, 'white'): 1}


def create_match(
    *,
    user,
    mode,
    opponent=None,
    difficulty='normal',
    stake_amount=0,
    time_limit_seconds=900,
    rematch_of=None,
    request_id=None,
):
    # Serialize same-player retries before checking caps or debiting their wallet.
    type(user).objects.select_for_update(no_key=True).get(pk=user.pk)
    request_id = request_id or uuid.uuid4()
    existing = CheckersMatch.objects.filter(white=user, request_id=request_id).first()
    if existing:
        if not (
            existing.mode == mode
            and existing.black_id == (opponent.id if opponent else None)
            and existing.difficulty == difficulty
            and existing.stake_amount == stake_amount
            and existing.time_limit_seconds == time_limit_seconds
            and existing.rematch_of_id == (rematch_of.id if rematch_of else None)
        ):
            raise StateConflict('This request ID was already used with different match settings.')
        return existing
    if CheckersMatch.objects.filter(white=user, status__in=UNFINISHED).count() >= 10:
        raise ValidationError('Finish or cancel an existing match before creating another (maximum 10).')
    currency = None
    if stake_amount:
        currency = Currency.objects.filter(ticker=settings.DEFAULT_CURRENCY_TICKER).first()
        if currency is None:
            raise ValidationError('TNB is not configured yet.')
    match = CheckersMatch.objects.create(
        white=user,
        black=opponent,
        mode=mode,
        difficulty=difficulty,
        currency=currency,
        stake_amount=stake_amount,
        prize_pool_total=stake_amount,
        time_limit_seconds=time_limit_seconds,
        clock_white_ms=time_limit_seconds * 1000,
        clock_black_ms=time_limit_seconds * 1000,
        expires_at=timezone.now() + timedelta(minutes=5),
        rematch_of=rematch_of,
        request_id=request_id,
    )
    _transfer(match, user.id, -stake_amount, 'stake')
    if mode == 'computer':
        _start_game(match)
    _record(match, 'created', initial=True)
    if mode == 'human':
        from .notifications import notify_challenge

        notify_challenge(match)
    return match


def close_challenge(match, status):
    if match.status != 'pending' or match.settled:
        raise StateConflict('This challenge is no longer pending.')
    _transfer(match, match.white_id, match.prize_pool_total, 'refund')
    match.settled = True
    match.status = status
    match.finished_at = timezone.now()
    _record(match, status)


def finish_match(match, winning_side, reason):
    if match.settled:
        raise StateConflict('The match has already settled.')
    if match.mode == 'computer':
        from thenewboston.game_rewards.services import settle_computer_reward

        match.computer_reward = settle_computer_reward(
            game='checkers',
            match_id=match.id,
            user_id=match.white_id,
            won=winning_side == 'white' and reason == 'no_moves',
        )
    if winning_side is None:
        # Stable lock ordering for draws in simultaneous matches with reversed players.
        if match.stake_amount:
            list(
                Wallet.objects.select_for_update()
                .filter(
                    currency_id=match.currency_id,
                    owner_id__in=[match.white_id, match.black_id],
                )
                .order_by('pk')
            )
        for user_id in (match.white_id, match.black_id):
            _transfer(match, user_id, match.stake_amount, 'refund')
    else:
        _transfer(match, getattr(match, f'{winning_side}_id'), match.prize_pool_total, 'payout')
    match.settled = True
    match.winner = winning_side
    match.status = 'finished'
    match.result_reason = reason
    match.finished_at = timezone.now()
    match.turn_started_at = None


def advance_deadlines(match):
    """Settle deadlines without changing running clocks during reads or sweeps."""
    now = timezone.now()
    if match.status == 'pending' and match.expires_at <= now:
        close_challenge(match, 'expired')
        return True
    if match.status != 'active':
        return False
    elapsed = max(0, int((now - match.turn_started_at).total_seconds() * 1000))
    if elapsed >= getattr(match, f'clock_{match.active_side}_ms'):
        losing_side = match.active_side
        setattr(match, f'clock_{losing_side}_ms', 0)
        finish_match(match, opponent(losing_side), 'timeout')
        _record(match, 'timeout', {'side': losing_side})
        return True
    return False


def make_move(match, side, path):
    if side != match.active_side:
        raise PermissionDenied('Wait for your turn.')
    try:
        board, captured = apply_move(match.board, side, path)
    except ValueError as error:
        raise ValidationError(str(error)) from error
    # Legal-move enumeration/search takes time; never accept a move after its clock.
    if advance_deadlines(match):
        return
    now = timezone.now()
    elapsed = max(0, int((now - match.turn_started_at).total_seconds() * 1000))
    clock_field = f'clock_{side}_ms'
    if elapsed >= getattr(match, clock_field):
        setattr(match, clock_field, 0)
        finish_match(match, opponent(side), 'timeout')
        _record(match, 'timeout', {'side': side})
        return
    setattr(match, clock_field, getattr(match, clock_field) - elapsed)
    irreversible = bool(captured) or abs(match.board[path[0]]) == 1
    match.reversible_plies = 0 if irreversible else match.reversible_plies + 1
    match.board = board
    match.active_side = opponent(side)
    match.turn_started_at = now
    match.last_move = {'side': side, 'path': path, 'captured': captured}
    key = position_key(board, match.active_side)
    # Before an irreversible move, earlier positions can never recur.
    match.position_counts = {} if irreversible else dict(match.position_counts)
    match.position_counts[key] = match.position_counts.get(key, 0) + 1
    if not legal_moves(board, match.active_side):
        finish_match(match, side, 'no_moves')
    elif match.position_counts[key] >= 3:
        finish_match(match, None, 'repetition')
    elif match.reversible_plies >= 80:
        finish_match(match, None, 'no_progress')
    _record(match, 'move', match.last_move)


def perform_action(match, user, action, data):
    side = player_side(match, user.id)
    if side is None:
        raise PermissionDenied('Only the players can change this match.')
    if data['expected_version'] != match.version:
        raise StateConflict()
    if advance_deadlines(match):
        return match
    if action in {'accept', 'decline', 'cancel'}:
        if match.status != 'pending':
            raise StateConflict('This challenge is no longer pending.')
        required_side = 'white' if action == 'cancel' else 'black'
        if side != required_side:
            raise PermissionDenied('Only the challenger can cancel; only the opponent can accept or decline.')
        if action == 'accept':
            _transfer(match, match.black_id, -match.stake_amount, 'stake')
            match.prize_pool_total += match.stake_amount
            _start_game(match)
            _record(match, 'accepted')
        else:
            close_challenge(match, 'cancelled' if action == 'cancel' else 'declined')
    elif action == 'rematch':
        if match.status != 'finished':
            raise StateConflict('Finish the current match before requesting a rematch.')
        existing = CheckersMatch.objects.filter(rematch_of=match, status__in=UNFINISHED).first()
        if existing:
            return existing
        other = match.black if side == 'white' else match.white
        return create_match(
            user=user,
            mode=match.mode,
            opponent=other,
            difficulty=match.difficulty,
            stake_amount=match.stake_amount,
            time_limit_seconds=match.time_limit_seconds,
            rematch_of=match,
        )
    else:
        if match.status != 'active':
            raise StateConflict('This match is not active.')
        if action == 'resign':
            finish_match(match, opponent(side), 'resignation')
            _record(match, 'resign', {'side': side})
        elif action == 'move':
            make_move(match, side, data['path'])
        else:
            raise ValidationError('Unknown match action.')
    queue_computer(match)
    return match


def computer_ready(match):
    return match.mode == 'computer' and match.status == 'active' and match.active_side == 'black'


def queue_computer(match):
    if not computer_ready(match):
        return
    from .tasks import play_computer_turn

    match_id, version = match.id, match.version

    def enqueue():
        try:
            play_computer_turn.delay(match_id, version)
        except Exception:
            # The committed human move stays successful; the periodic sweep retries.
            logger.exception('Could not enqueue checkers computer turn for match %s', match_id)

    apply_on_commit(enqueue)


@transaction.atomic
def run_computer(match_id, expected_version):
    from .ai import choose_move

    match = CheckersMatch.objects.select_for_update().filter(pk=match_id).first()
    if match is None or match.version != expected_version or not computer_ready(match) or advance_deadlines(match):
        return
    path = choose_move(match.board, 'black', match.difficulty)
    if not advance_deadlines(match):
        make_move(match, 'black', path)
