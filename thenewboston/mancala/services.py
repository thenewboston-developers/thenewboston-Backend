"""Server-authoritative match transitions and transactional fixed-stake accounting.

Callers hold the match row lock and a transaction before changing an existing
match. Wallet changes and their ledger records share that transaction.
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

from .models import MancalaEvent, MancalaLedgerEntry, MancalaMatch
from .rules import initial_board, leader, opponent, sow

UNFINISHED = ['pending', 'active']
logger = logging.getLogger(__name__)


class StateConflict(APIException):
    status_code = 409
    default_detail = 'The match changed. Refresh it before trying again.'


def player_side(match, user_id, guest_session=None):
    if match.guest_session_id:
        # A signed-out visitor's game: only the session that started it plays, always as the host.
        return 'host' if owns_guest_match(match, guest_session) else None
    if user_id is not None and user_id == match.host_id:
        return 'host'
    if user_id is not None and user_id == match.guest_id:
        return 'guest'
    return None


def _transfer(match, user_id, amount, action):
    if not amount:
        return
    wallet = Wallet.objects.select_for_update().filter(currency_id=match.currency_id, owner_id=user_id).first()
    if wallet is None:
        raise ValidationError('A TNB wallet is required for a staked match.')
    if wallet.balance + amount < 0:
        raise ValidationError('Insufficient TNB balance for this stake.')
    MancalaLedgerEntry.objects.create(match=match, wallet=wallet, amount=amount, action=action)
    wallet.change_balance(amount, should_stream=True)


def _record(match, event_type, payload=None, *, initial=False):
    if not initial:
        match.version += 1
    match.save()
    MancalaEvent.objects.create(match=match, version=match.version, event_type=event_type, payload=payload or {})


def _start_game(match):
    match.status = 'active'
    match.board = initial_board()
    # Moving first is an advantage, so neither the challenger nor the computer gets it by default.
    match.active_side = 'host' if randbelow(2) == 0 else 'guest'
    match.turn_started_at = timezone.now()


def create_match(
    *,
    user,
    mode,
    opponent=None,
    difficulty='normal',
    stake_amount=0,
    time_limit_seconds=600,
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
    existing = MancalaMatch.objects.filter(**owner, request_id=request_id).first()
    if existing:
        if not (
            existing.mode == mode
            and existing.guest_id == (opponent.id if opponent else None)
            and existing.difficulty == difficulty
            and existing.stake_amount == stake_amount
            and existing.time_limit_seconds == time_limit_seconds
            and existing.rematch_of_id == (rematch_of.id if rematch_of else None)
        ):
            raise StateConflict('This request ID was already used with different match settings.')
        return existing
    if MancalaMatch.objects.filter(**owner, status__in=UNFINISHED).count() >= 10:
        raise ValidationError('Finish or cancel an existing match before creating another (maximum 10).')
    currency = None
    if stake_amount:
        currency = Currency.objects.filter(ticker=settings.DEFAULT_CURRENCY_TICKER).first()
        if currency is None:
            raise ValidationError('TNB is not configured yet.')
    match = MancalaMatch.objects.create(
        host=user,
        guest_session=guest_session,
        guest=opponent,
        mode=mode,
        difficulty=difficulty,
        currency=currency,
        stake_amount=stake_amount,
        prize_pool_total=stake_amount,
        time_limit_seconds=time_limit_seconds,
        clock_host_ms=time_limit_seconds * 1000,
        clock_guest_ms=time_limit_seconds * 1000,
        expires_at=timezone.now() + timedelta(minutes=5),
        rematch_of=rematch_of,
        request_id=request_id,
    )
    _transfer(match, user.id if user else None, -stake_amount, 'stake')
    if mode == 'computer':
        _start_game(match)
    _record(match, 'created', {'first': match.active_side}, initial=True)
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
    """Settle the match. Without a winning side the game is a draw and both stakes go back."""
    if match.settled:
        raise StateConflict('The match has already settled.')
    if match.mode == 'computer':
        from thenewboston.game_rewards.services import settle_computer_reward

        # Only a game played to the end counts: not a timeout, a resignation, or a draw.
        # A signed-out visitor has no host account, which makes the reward informational only.
        match.computer_reward = settle_computer_reward(
            game='mancala',
            match_id=match.id,
            user_id=match.host_id,
            won=winning_side == 'host' and reason == 'stones',
        )
    if winning_side is None:
        if match.stake_amount:
            # Order the two wallet locks consistently even when other matches reverse the players.
            list(
                Wallet.objects.select_for_update()
                .filter(currency_id=match.currency_id, owner_id__in=[match.host_id, match.guest_id])
                .order_by('pk')
            )
        for user_id in (match.host_id, match.guest_id):
            _transfer(match, user_id, match.stake_amount, 'refund')
    else:
        _transfer(match, getattr(match, f'{winning_side}_id'), match.prize_pool_total, 'payout')
    match.settled = True
    match.winner = winning_side
    match.status = 'finished'
    match.result_reason = reason
    match.finished_at = timezone.now()
    match.turn_started_at = None
    match.active_side = None


def deadline_passed(match):
    """A read-only check, so polling a healthy match never takes its row lock."""
    now = timezone.now()
    if match.status == 'pending':
        return match.expires_at <= now
    if match.status != 'active':
        return False
    elapsed = (now - match.turn_started_at).total_seconds() * 1000
    return elapsed >= getattr(match, f'clock_{match.active_side}_ms')


def advance_deadlines(match):
    """Settle an expired challenge or a clock that ran out. Running clocks are left untouched."""
    if not deadline_passed(match):
        return False
    if match.status == 'pending':
        close_challenge(match, 'expired')
        return True
    losing_side = match.active_side
    setattr(match, f'clock_{losing_side}_ms', 0)
    finish_match(match, opponent(losing_side), 'timeout')
    _record(match, 'timeout', {'side': losing_side})
    return True


def play(match, side, pit):
    if match.active_side != side:
        raise PermissionDenied('Wait for your turn.')
    try:
        board, move = sow(match.board, side, pit)
    except ValueError as error:
        raise ValidationError(str(error)) from error
    now = timezone.now()
    elapsed = max(0, int((now - match.turn_started_at).total_seconds() * 1000))
    if elapsed >= getattr(match, f'clock_{side}_ms'):
        setattr(match, f'clock_{side}_ms', 0)
        finish_match(match, opponent(side), 'timeout')
        _record(match, 'timeout', {'side': side})
        return
    setattr(match, f'clock_{side}_ms', getattr(match, f'clock_{side}_ms') - elapsed)
    match.board = board
    match.last_move = move
    if move['swept'] is not None:
        winning_side = leader(board)
        finish_match(match, winning_side, 'stones' if winning_side else 'draw')
    else:
        match.active_side = side if move['extra_turn'] else opponent(side)
        match.turn_started_at = now
    # The board is stored with the move so a client can replay moves it missed between polls.
    _record(match, 'move', {**move, 'board': board})


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
        required_side = 'host' if action == 'cancel' else 'guest'
        if side != required_side:
            raise PermissionDenied('Only the challenger can cancel; only the opponent can accept or decline.')
        if action == 'accept':
            _transfer(match, match.guest_id, -match.stake_amount, 'stake')
            match.prize_pool_total += match.stake_amount
            _start_game(match)
            _record(match, 'accepted', {'first': match.active_side})
        else:
            close_challenge(match, 'cancelled' if action == 'cancel' else 'declined')
    elif action == 'rematch':
        if match.status != 'finished':
            raise StateConflict('Finish the current match before requesting a rematch.')
        existing = MancalaMatch.objects.filter(rematch_of=match, status__in=UNFINISHED).first()
        if existing:
            return existing
        other = match.guest if side == 'host' else match.host
        return create_match(
            user=user,
            mode=match.mode,
            opponent=other,
            difficulty=match.difficulty,
            stake_amount=match.stake_amount,
            time_limit_seconds=match.time_limit_seconds,
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
            play(match, side, data['pit'])
        else:
            raise ValidationError('Unknown match action.')
    queue_computer(match)
    return match


def computer_ready(match):
    return match.mode == 'computer' and match.status == 'active' and match.active_side == 'guest'


def queue_computer(match):
    if not computer_ready(match):
        return
    from .tasks import play_computer_turn

    match_id, version = match.id, match.version

    def enqueue():
        try:
            play_computer_turn.delay(match_id, version)
        except Exception:
            # A committed human move must remain successful if the broker is down.
            # The periodic sweep retries delivery from the persisted match state.
            logger.exception('Could not enqueue mancala computer turn for match %s', match_id)

    apply_on_commit(enqueue)


@transaction.atomic
def run_computer(match_id, expected_version):
    from .ai import choose_pit

    match = MancalaMatch.objects.select_for_update().filter(pk=match_id).first()
    if match is None or match.version != expected_version or not computer_ready(match) or advance_deadlines(match):
        return
    play(match, 'guest', choose_pit(match.board, 'guest', match.difficulty))
    # Ending in its own store gives the computer another turn, played as a separate step.
    queue_computer(match)
