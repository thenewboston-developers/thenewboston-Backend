"""Server-authoritative match transitions and transactional fixed-stake accounting.

Callers hold the match row lock and a transaction before changing an existing
match. Private fleets remain in the database and never enter the event log.
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

from .models import BattleshipEvent, BattleshipLedgerEntry, BattleshipMatch
from .rules import opponent, random_fleet, resolve_shot, sunk_ships, validate_fleet

UNFINISHED = ['pending', 'active']
logger = logging.getLogger(__name__)


class StateConflict(APIException):
    status_code = 409
    default_detail = 'The match changed. Refresh it before trying again.'


def player_side(match, user_id, guest_session=None):
    if match.guest_session_id:
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
    BattleshipLedgerEntry.objects.create(match=match, wallet=wallet, amount=amount, action=action)
    wallet.change_balance(amount, should_stream=True)


def _record(match, event_type, payload=None, *, initial=False):
    if not initial:
        match.version += 1
    match.save()
    BattleshipEvent.objects.create(match=match, version=match.version, event_type=event_type, payload=payload or {})


def _start_placement(match):
    match.status = 'active'
    match.phase = 'placing'
    match.placement_deadline = timezone.now() + timedelta(minutes=5)
    if match.mode == 'computer':
        match.fleet_guest = random_fleet()


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
    guest_session=None,
):
    # Serialize creates from this player, including retries, before debiting money.
    owner = match_owner(user, guest_session, 'host')
    if guest_session and (mode != 'computer' or stake_amount or opponent):
        raise PermissionDenied('Guests can only play free computer games.')
    lock_match_owner(user, guest_session)
    request_id = request_id or uuid.uuid4()
    existing = BattleshipMatch.objects.filter(**owner, request_id=request_id).first()
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
    if BattleshipMatch.objects.filter(**owner, status__in=UNFINISHED).count() >= 10:
        raise ValidationError('Finish or cancel an existing match before creating another (maximum 10).')
    currency = None
    if stake_amount:
        currency = Currency.objects.filter(ticker=settings.DEFAULT_CURRENCY_TICKER).first()
        if currency is None:
            raise ValidationError('TNB is not configured yet.')
    match = BattleshipMatch.objects.create(
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
        _start_placement(match)
    _record(match, 'created', initial=True)
    if mode == 'human':
        from .notifications import notify_challenge

        notify_challenge(match)
    return match


def close_challenge(match, status):
    if match.status != 'pending' or match.settled:
        raise StateConflict('This challenge is no longer pending.')
    _transfer(match, match.host_id, match.prize_pool_total, 'refund')
    match.settled = True
    match.status = status
    match.phase = 'finished'
    match.finished_at = timezone.now()
    _record(match, status)


def finish_match(match, winning_side, reason):
    if match.settled:
        raise StateConflict('The match has already settled.')
    if match.mode == 'computer':
        from thenewboston.game_rewards.services import settle_computer_reward

        match.computer_reward = settle_computer_reward(
            game='battleship',
            match_id=match.id,
            user_id=match.host_id,
            won=winning_side == 'host' and reason in {'fleet_sunk'},
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
        _transfer(match, getattr(match, f'{winning_side}_id'), match.prize_pool_total, 'payout')
    match.settled = True
    match.winner = winning_side
    match.status = 'finished'
    match.phase = 'finished'
    match.result_reason = reason
    match.finished_at = timezone.now()
    match.turn_started_at = None
    match.active_side = None


def advance_deadlines(match):
    """Settle expired matches; leave running clocks untouched until a move commits."""
    now = timezone.now()
    if match.status == 'pending' and match.expires_at <= now:
        close_challenge(match, 'expired')
        return True
    if match.status != 'active':
        return False
    if match.phase == 'placing' and match.placement_deadline <= now:
        ready = [side for side in ('host', 'guest') if getattr(match, f'fleet_{side}')]
        winning_side = ready[0] if len(ready) == 1 else None
        reason = 'placement_timeout' if winning_side else 'placement_abandoned'
        finish_match(match, winning_side, reason)
        _record(match, reason)
        return True
    if match.phase == 'battle':
        elapsed = max(0, int((now - match.turn_started_at).total_seconds() * 1000))
        if elapsed >= getattr(match, f'clock_{match.active_side}_ms'):
            losing_side = match.active_side
            setattr(match, f'clock_{losing_side}_ms', 0)
            finish_match(match, opponent(losing_side), 'timeout')
            _record(match, 'timeout', {'side': losing_side})
            return True
    return False


def place_fleet(match, side, ships):
    if match.phase != 'placing' or getattr(match, f'fleet_{side}'):
        raise StateConflict('Your fleet is already locked or placement has ended.')
    try:
        fleet = validate_fleet(ships)
    except ValueError as error:
        raise ValidationError(str(error)) from error
    setattr(match, f'fleet_{side}', fleet)
    if match.fleet_host and match.fleet_guest:
        match.phase = 'battle'
        match.active_side = 'host' if randbelow(2) == 0 else 'guest'
        match.turn_started_at = timezone.now()
    _record(match, 'placed', {'side': side})


def fire(match, side, row, column):
    if match.phase != 'battle' or match.active_side != side:
        raise PermissionDenied('Wait for your turn to fire.')
    shots = getattr(match, f'shots_{side}')
    try:
        shot, won = resolve_shot(getattr(match, f'fleet_{opponent(side)}'), shots, row, column)
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
    setattr(match, f'shots_{side}', [*shots, shot])
    match.last_shot = {'side': side, **shot}
    if won:
        finish_match(match, side, 'fleet_sunk')
    else:
        match.active_side = opponent(side)
        match.turn_started_at = now
    _record(match, 'shot', match.last_shot)


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
            _start_placement(match)
            _record(match, 'accepted')
        else:
            close_challenge(match, 'cancelled' if action == 'cancel' else 'declined')
    elif action == 'rematch':
        if match.status != 'finished':
            raise StateConflict('Finish the current match before requesting a rematch.')
        existing = BattleshipMatch.objects.filter(rematch_of=match, status__in=UNFINISHED).first()
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
        elif action == 'place':
            place_fleet(match, side, data['ships'])
        elif action == 'fire':
            fire(match, side, data['row'], data['column'])
        else:
            raise ValidationError('Unknown match action.')
    queue_computer(match)
    return match


def computer_ready(match):
    return (
        match.mode == 'computer'
        and match.status == 'active'
        and match.phase == 'battle'
        and match.active_side == 'guest'
    )


def queue_computer(match):
    if not computer_ready(match):
        return
    from .tasks import play_computer_turn

    match_id, version = match.id, match.version

    def enqueue():
        try:
            play_computer_turn.delay(match_id, version)
        except Exception:
            logger.exception('Could not enqueue battleship computer turn for match %s', match_id)

    apply_on_commit(enqueue)


@transaction.atomic
def run_computer(match_id, expected_version):
    from .ai import choose_shot

    match = BattleshipMatch.objects.select_for_update().filter(pk=match_id).first()
    if match is None or match.version != expected_version or not computer_ready(match) or advance_deadlines(match):
        return
    # Only sunk placements are public. The strategy never receives the private fleet.
    row, column = choose_shot(match.shots_guest, sunk_ships(match.fleet_host, match.shots_guest), match.difficulty)
    if not advance_deadlines(match):
        fire(match, 'guest', row, column)
