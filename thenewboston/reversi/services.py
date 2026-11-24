"""Server-authoritative match transitions and transactional fixed-stake accounting.

Callers hold the match row lock and a transaction before changing an existing
match. Wallet changes and ledger records share that transaction.
"""

import logging
import uuid
from datetime import timedelta
from secrets import randbelow

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from thenewboston.currencies.models import Currency
from thenewboston.general.guest_games import lock_match_owner, match_owner, owns_guest_match
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.wallets.models import Wallet

from .models import ReversiEvent, ReversiLedgerEntry, ReversiMatch
from .rules import apply_move, leader, next_side, opponent as other_side

UNFINISHED = ['pending', 'active']
logger = logging.getLogger(__name__)


class StateConflict(APIException):
    status_code = 409
    default_detail = 'The match changed. Refresh it before trying again.'


def player_side(match, user_id, guest_session=None):
    """The color a requester plays, or None for anyone who is not a player."""
    if match.guest_session_id:
        return match.host_side if owns_guest_match(match, guest_session) else None
    if user_id is None:
        return None
    if user_id == match.host_id:
        return match.host_side
    if user_id == match.guest_id:
        return other_side(match.host_side)
    return None


def side_user_id(match, side):
    """The user playing a color. None is the computer, or the visitor of a guest game."""
    return match.host_id if side == match.host_side else match.guest_id


def _transfer(match, user_id, amount, action):
    if not amount:
        return
    wallet = Wallet.objects.select_for_update().filter(currency_id=match.currency_id, owner_id=user_id).first()
    if wallet is None:
        raise ValidationError('A TNB wallet is required for a staked match.')
    if wallet.balance + amount < 0:
        raise ValidationError('Insufficient TNB balance for this stake.')
    ReversiLedgerEntry.objects.create(match=match, wallet=wallet, amount=amount, action=action)
    wallet.change_balance(amount, should_stream=True)


def _record(match, event_type, payload=None, *, initial=False):
    if not initial:
        match.version += 1
    match.save()
    ReversiEvent.objects.create(match=match, version=match.version, event_type=event_type, payload=payload or {})


def _start(match):
    match.status = 'active'
    match.active_side = 'black'
    match.turn_started_at = timezone.now()


def create_match(
    *,
    user,
    mode,
    opponent=None,
    difficulty='normal',
    color='random',
    stake_amount=0,
    time_limit_seconds=900,
    rematch_of=None,
    request_id=None,
    guest_session=None,
):
    owner = match_owner(user, guest_session, 'host')
    if guest_session and (mode != 'computer' or stake_amount or opponent):
        raise PermissionDenied('Guests can only play free computer games.')
    # Serialize creates from this player, including retries, before debiting money.
    lock_match_owner(user, guest_session)
    request_id = request_id or uuid.uuid4()
    existing = ReversiMatch.objects.filter(**owner, request_id=request_id).first()
    if existing:
        if not (
            existing.mode == mode
            and existing.guest_id == (opponent.id if opponent else None)
            and existing.difficulty == difficulty
            and color in ('random', existing.host_side)
            and existing.stake_amount == stake_amount
            and existing.time_limit_seconds == time_limit_seconds
            and existing.rematch_of_id == (rematch_of.id if rematch_of else None)
        ):
            raise StateConflict('This request ID was already used with different match settings.')
        return existing
    if ReversiMatch.objects.filter(**owner, status__in=UNFINISHED).count() >= 10:
        raise ValidationError('Finish or cancel an existing match before creating another (maximum 10).')
    currency = None
    if stake_amount:
        currency = Currency.objects.filter(ticker=settings.DEFAULT_CURRENCY_TICKER).first()
        if currency is None:
            raise ValidationError('TNB is not configured yet.')
    if color == 'random':
        color = 'black' if randbelow(2) == 0 else 'white'
    match = ReversiMatch.objects.create(
        host=user,
        guest_session=guest_session,
        guest=opponent,
        mode=mode,
        difficulty=difficulty,
        host_side=color,
        currency=currency,
        stake_amount=stake_amount,
        prize_pool_total=stake_amount,
        time_limit_seconds=time_limit_seconds,
        clock_black_ms=time_limit_seconds * 1000,
        clock_white_ms=time_limit_seconds * 1000,
        expires_at=timezone.now() + timedelta(minutes=5),
        rematch_of=rematch_of,
        request_id=request_id,
    )
    _transfer(match, user.id if user else None, -stake_amount, 'stake')
    if mode == 'computer':
        _start(match)
    _record(match, 'created', {'host_side': match.host_side}, initial=True)
    if mode == 'human':
        from .notifications import notify_challenge

        notify_challenge(match)
    queue_computer(match)
    return match


def close_challenge(match, status):
    if match.status != 'pending' or match.settled:
        raise StateConflict('This challenge is no longer pending.')
    _transfer(match, match.host_id, match.prize_pool_total, 'refund')
    match.settled = True
    match.status = status
    match.finished_at = timezone.now()
    _record(match, status)


def finish_match(match, winning_side, reason):
    """Settle the prize. A winning side of None is a draw: every stake goes back to its player."""
    if match.settled:
        raise StateConflict('The match has already settled.')
    if match.mode == 'computer':
        from thenewboston.game_rewards.services import settle_computer_reward

        match.computer_reward = settle_computer_reward(
            game='reversi',
            match_id=match.id,
            user_id=match.host_id,
            won=winning_side == match.host_side and reason == 'disk_count',
        )
    if winning_side is None:
        # Order the two wallet locks consistently even when other matches reverse players.
        if match.stake_amount:
            list(
                Wallet.objects.select_for_update()
                .filter(currency_id=match.currency_id, owner_id__in=[match.host_id, match.guest_id])
                .order_by('pk')
            )
        for user_id in (match.host_id, match.guest_id):
            _transfer(match, user_id, match.stake_amount, 'refund')
    else:
        _transfer(match, side_user_id(match, winning_side), match.prize_pool_total, 'payout')
    match.settled = True
    match.winner = winning_side
    match.status = 'finished'
    match.result_reason = reason
    match.finished_at = timezone.now()
    match.turn_started_at = None
    match.active_side = None


def _elapsed_ms(match, now):
    return max(0, int((now - match.turn_started_at).total_seconds() * 1000))


def _time_out(match, side):
    setattr(match, f'clock_{side}_ms', 0)
    finish_match(match, other_side(side), 'timeout')
    _record(match, 'timeout', {'side': side})


def deadline_passed(match):
    """Whether a challenge expired or the moving player's clock ran out. Reads only; safe without the row lock."""
    now = timezone.now()
    if match.status == 'pending':
        return match.expires_at <= now
    if match.status != 'active':
        return False
    return _elapsed_ms(match, now) >= getattr(match, f'clock_{match.active_side}_ms')


def advance_deadlines(match):
    """Settle an expired challenge or a clock that ran out. Running clocks are only written when a move commits."""
    if not deadline_passed(match):
        return False
    if match.status == 'pending':
        close_challenge(match, 'expired')
    else:
        _time_out(match, match.active_side)
    return True


def play(match, side, row, column):
    if match.active_side != side:
        raise PermissionDenied('Wait for your turn.')
    try:
        board, flipped = apply_move(match.board, side, row, column)
    except ValueError as error:
        raise ValidationError(str(error)) from error
    now = timezone.now()
    elapsed = _elapsed_ms(match, now)
    clock = f'clock_{side}_ms'
    if elapsed >= getattr(match, clock):
        _time_out(match, side)
        return
    setattr(match, clock, getattr(match, clock) - elapsed)
    match.board = board
    match.move_count += 1
    following = next_side(board, side)
    # A player without a legal move passes automatically, so the same side moves again.
    passed = other_side(side) if following == side else None
    match.last_move = {'side': side, 'row': row, 'column': column, 'flipped': flipped, 'passed': passed}
    if following is None:
        winning_side = leader(board)
        finish_match(match, winning_side, 'disk_count' if winning_side else 'draw')
    else:
        match.active_side = following
        match.turn_started_at = now
    _record(match, 'move', match.last_move)


def perform_action(match, user, action, data, guest_session=None):
    side = player_side(match, user.id if user else None, guest_session)
    if side is None:
        raise PermissionDenied('Only the players can change this match.')
    if data['expected_version'] != match.version:
        raise StateConflict()
    if advance_deadlines(match):
        return match
    # The creator always plays `host_side`, whether a member or a guest.
    is_host = side == match.host_side
    if action in {'accept', 'decline', 'cancel'}:
        if match.status != 'pending':
            raise StateConflict('This challenge is no longer pending.')
        if is_host != (action == 'cancel'):
            raise PermissionDenied('Only the challenger can cancel; only the opponent can accept or decline.')
        if action == 'accept':
            _transfer(match, match.guest_id, -match.stake_amount, 'stake')
            match.prize_pool_total += match.stake_amount
            _start(match)
            _record(match, 'accepted')
        else:
            close_challenge(match, 'cancelled' if action == 'cancel' else 'declined')
    elif action == 'rematch':
        if match.status != 'finished':
            raise StateConflict('Finish the current match before requesting a rematch.')
        existing = ReversiMatch.objects.filter(rematch_of=match, status__in=UNFINISHED).first()
        if existing:
            return existing
        return create_match(
            user=user,
            mode=match.mode,
            opponent=match.guest if is_host else match.host,
            difficulty=match.difficulty,
            # Players trade colors for a human rematch; a computer game keeps the chosen color.
            color=side if match.mode == 'computer' else other_side(side),
            stake_amount=match.stake_amount,
            time_limit_seconds=match.time_limit_seconds,
            rematch_of=match,
            guest_session=guest_session,
        )
    else:
        if match.status != 'active':
            raise StateConflict('This match is not active.')
        if action == 'resign':
            finish_match(match, other_side(side), 'resignation')
            _record(match, 'resign', {'side': side})
        elif action == 'move':
            play(match, side, data['row'], data['column'])
        else:
            raise ValidationError('Unknown match action.')
    queue_computer(match)
    return match


def computer_ready(match):
    return match.mode == 'computer' and match.status == 'active' and match.active_side != match.host_side


def queue_computer(match):
    if not computer_ready(match):
        return
    from .tasks import play_computer_turn

    match_id, version = match.id, match.version

    def enqueue():
        try:
            play_computer_turn.delay(match_id, version)
        except Exception:
            # A committed human move must stay successful if the broker is down.
            # The periodic sweep retries delivery from the persisted match state.
            logger.exception('Could not enqueue reversi computer turn for match %s', match_id)

    apply_on_commit(enqueue)


def run_computer(match_id, expected_version):
    from .ai import choose_move

    # Think before taking the row lock, so reads and resignations never wait on the search.
    snapshot = ReversiMatch.objects.filter(pk=match_id).first()
    if snapshot is None or snapshot.version != expected_version or not computer_ready(snapshot):
        return
    side = snapshot.active_side
    row, column = choose_move(snapshot.board, side, snapshot.difficulty)
    with transaction.atomic():
        match = ReversiMatch.objects.select_for_update().filter(pk=match_id).first()
        # An unchanged version means the board the move was chosen for is still the current one.
        if match is None or match.version != expected_version or not computer_ready(match):
            return
        if advance_deadlines(match):
            return
        play(match, side, row, column)
        queue_computer(match)
