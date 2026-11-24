"""Authoritative Hex transitions with locked, atomic stake settlement.

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
from thenewboston.general.guest_games import lock_match_owner, match_owner, owns_guest_match
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.wallets.models import Wallet

from .models import HexEvent, HexLedgerEntry, HexMatch
from .rules import empty_board, opponent, place, swap, winning_path

UNFINISHED = ['pending', 'active']
logger = logging.getLogger(__name__)


class StateConflict(APIException):
    status_code = 409
    default_detail = 'The match changed. Refresh it before trying again.'


def player_side(match, user_id, guest_session=None):
    if match.guest_session_id:
        return 'red' if owns_guest_match(match, guest_session) else None
    if user_id is not None and user_id == match.red_id:
        return 'red'
    if user_id is not None and user_id == match.blue_id:
        return 'blue'
    return None


def can_swap(match):
    """Blue may take over Red's opening stone, but only between two players and only as the reply to it."""
    return match.mode == 'human' and match.status == 'active' and match.move_count == 1 and match.active_side == 'blue'


def _transfer(match, user_id, amount, action):
    if not amount:
        return
    wallet = Wallet.objects.select_for_update().filter(currency_id=match.currency_id, owner_id=user_id).first()
    if wallet is None:
        raise ValidationError('A TNB wallet is required for a staked match.')
    if wallet.balance + amount < 0:
        raise ValidationError('Insufficient TNB balance for this stake.')
    HexLedgerEntry.objects.create(match=match, wallet=wallet, amount=amount, action=action)
    wallet.change_balance(amount, should_stream=True)


def _record(match, event_type, payload=None, *, initial=False):
    if not initial:
        match.version += 1
    match.save()
    HexEvent.objects.create(match=match, version=match.version, event_type=event_type, payload=payload or {})


def _start_game(match):
    match.status = 'active'
    match.board = empty_board(match.board_size)
    match.move_count = 0
    match.active_side = 'red'
    match.turn_started_at = timezone.now()


def create_match(
    *,
    user,
    mode,
    opponent=None,
    difficulty='normal',
    stake_amount=0,
    time_limit_seconds=900,
    board_size=11,
    rematch_of=None,
    request_id=None,
    guest_session=None,
):
    # Serialize same-player retries before checking caps or debiting their wallet.
    owner = match_owner(user, guest_session, 'red')
    if guest_session and (mode != 'computer' or stake_amount or opponent):
        raise PermissionDenied('Guests can only play free computer games.')
    lock_match_owner(user, guest_session)
    request_id = request_id or uuid.uuid4()
    existing = HexMatch.objects.filter(**owner, request_id=request_id).first()
    if existing:
        if not (
            existing.mode == mode
            and existing.blue_id == (opponent.id if opponent else None)
            and existing.difficulty == difficulty
            and existing.stake_amount == stake_amount
            and existing.time_limit_seconds == time_limit_seconds
            and existing.board_size == board_size
            and existing.rematch_of_id == (rematch_of.id if rematch_of else None)
        ):
            raise StateConflict('This request ID was already used with different match settings.')
        return existing
    if HexMatch.objects.filter(**owner, status__in=UNFINISHED).count() >= 10:
        raise ValidationError('Finish or cancel an existing match before creating another (maximum 10).')
    currency = None
    if stake_amount:
        currency = Currency.objects.filter(ticker=settings.DEFAULT_CURRENCY_TICKER).first()
        if currency is None:
            raise ValidationError('TNB is not configured yet.')
    match = HexMatch.objects.create(
        red=user,
        guest_session=guest_session,
        blue=opponent,
        mode=mode,
        difficulty=difficulty,
        currency=currency,
        stake_amount=stake_amount,
        prize_pool_total=stake_amount,
        board_size=board_size,
        board=empty_board(board_size),
        time_limit_seconds=time_limit_seconds,
        clock_red_ms=time_limit_seconds * 1000,
        clock_blue_ms=time_limit_seconds * 1000,
        expires_at=timezone.now() + timedelta(minutes=5),
        rematch_of=rematch_of,
        request_id=request_id,
    )
    _transfer(match, user.id if user else None, -stake_amount, 'stake')
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
    _transfer(match, match.red_id, match.prize_pool_total, 'refund')
    match.settled = True
    match.status = status
    match.finished_at = timezone.now()
    _record(match, status)


def finish_match(match, winning_side, reason):
    """Hex has no draws: every finished match has a winner who takes the whole prize pool."""
    if match.settled:
        raise StateConflict('The match has already settled.')
    if match.mode == 'computer':
        from thenewboston.game_rewards.services import settle_computer_reward

        match.computer_reward = settle_computer_reward(
            game='hex',
            match_id=match.id,
            user_id=match.red_id,
            won=winning_side == 'red' and reason == 'connection',
        )
    _transfer(match, getattr(match, f'{winning_side}_id'), match.prize_pool_total, 'payout')
    match.settled = True
    match.winner = winning_side
    match.status = 'finished'
    match.result_reason = reason
    match.finished_at = timezone.now()
    match.turn_started_at = None


def _time_out(match, side):
    setattr(match, f'clock_{side}_ms', 0)
    finish_match(match, opponent(side), 'timeout')
    _record(match, 'timeout', {'side': side})


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
        _time_out(match, match.active_side)
        return True
    return False


def make_move(match, side, cell=None, *, swapping=False):
    if side != match.active_side:
        raise PermissionDenied('Wait for your turn.')
    try:
        if swapping:
            if not can_swap(match):
                raise ValueError(
                    'Only Blue can swap, and only as the reply to the first stone of a match between players.'
                )
            board, origin, cell = swap(match.board, match.board_size)
            move = {'side': side, 'cell': cell, 'swap': True, 'from': origin}
        else:
            board = place(match.board, match.board_size, side, cell)
            move = {'side': side, 'cell': cell, 'swap': False}
    except ValueError as error:
        raise ValidationError(str(error)) from error
    # Choosing a move takes time; never accept one after its clock.
    if advance_deadlines(match):
        return
    now = timezone.now()
    elapsed = max(0, int((now - match.turn_started_at).total_seconds() * 1000))
    clock_field = f'clock_{side}_ms'
    if elapsed >= getattr(match, clock_field):
        _time_out(match, side)
        return
    setattr(match, clock_field, getattr(match, clock_field) - elapsed)
    match.board = board
    match.move_count += 1
    match.active_side = opponent(side)
    match.turn_started_at = now
    match.last_move = move
    if path := winning_path(board, match.board_size, side):
        match.winning_path = path
        finish_match(match, side, 'connection')
    _record(match, 'swap' if swapping else 'move', move)


def perform_action(match, user, action, data, guest_session=None):
    side = player_side(match, user.id if user else None, guest_session)
    if side is None:
        raise PermissionDenied('Only the players can change this match.')
    if data['expected_version'] != match.version:
        raise StateConflict()
    if advance_deadlines(match):
        return match
    if action in {'accept', 'decline', 'cancel'}:
        if match.status != 'pending':
            raise StateConflict('This challenge is no longer pending.')
        required_side = 'red' if action == 'cancel' else 'blue'
        if side != required_side:
            raise PermissionDenied('Only the challenger can cancel; only the opponent can accept or decline.')
        if action == 'accept':
            _transfer(match, match.blue_id, -match.stake_amount, 'stake')
            match.prize_pool_total += match.stake_amount
            _start_game(match)
            _record(match, 'accepted')
        else:
            close_challenge(match, 'cancelled' if action == 'cancel' else 'declined')
    elif action == 'rematch':
        if match.status != 'finished':
            raise StateConflict('Finish the current match before requesting a rematch.')
        existing = HexMatch.objects.filter(rematch_of=match, status__in=UNFINISHED).first()
        if existing:
            return existing
        other = match.blue if side == 'red' else match.red
        return create_match(
            user=user,
            mode=match.mode,
            opponent=other,
            difficulty=match.difficulty,
            stake_amount=match.stake_amount,
            time_limit_seconds=match.time_limit_seconds,
            board_size=match.board_size,
            rematch_of=match,
            guest_session=guest_session,
        )
    else:
        if match.status != 'active':
            raise StateConflict('This match is not active.')
        if action == 'resign':
            finish_match(match, opponent(side), 'resignation')
            _record(match, 'resign', {'side': side})
        elif action == 'move':
            make_move(match, side, data['cell'])
        elif action == 'swap':
            make_move(match, side, swapping=True)
        else:
            raise ValidationError('Unknown match action.')
    queue_computer(match)
    return match


def computer_ready(match):
    return match.mode == 'computer' and match.status == 'active' and match.active_side == 'blue'


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
            logger.exception('Could not enqueue hex computer turn for match %s', match_id)

    apply_on_commit(enqueue)


def run_computer(match_id, expected_version):
    from .ai import choose_move

    # Think before taking the row lock, so reads and the player's own requests never wait on the search.
    snapshot = HexMatch.objects.filter(pk=match_id).first()
    if snapshot is None or snapshot.version != expected_version or not computer_ready(snapshot):
        return
    cell = choose_move(snapshot.board, snapshot.board_size, 'blue', snapshot.difficulty)
    with transaction.atomic():
        match = HexMatch.objects.select_for_update().filter(pk=match_id).first()
        # Same version means the same board: the cell was chosen for exactly this position.
        if match is None or match.version != expected_version or not computer_ready(match):
            return
        if not advance_deadlines(match):
            make_move(match, 'blue', cell)
