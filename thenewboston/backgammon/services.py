"""Authoritative game transitions and fixed-match TNB accounting.

Every existing-match mutation holds that match's row lock. Wallet mutations and
ledger records share its transaction. The cube changes points, never the stake.
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

from .models import BackgammonEvent, BackgammonLedgerEntry, BackgammonMatch
from .rules import apply_turn, initial_board, opponent, win_points, winner

UNFINISHED = ['pending', 'active', 'between_games']
logger = logging.getLogger(__name__)


class StateConflict(APIException):
    status_code = 409
    default_detail = 'The match changed. Refresh it before trying again.'


def player_side(match, user_id, guest_session=None):
    if match.guest_session_id:
        return 'white' if owns_guest_match(match, guest_session) else None
    if user_id is not None and user_id == match.white_id:
        return 'white'
    if user_id is not None and user_id == match.black_id:
        return 'black'
    return None


def clock_side(match):
    if match.status != 'active':
        return None
    return opponent(match.double_offered_by) if match.double_offered_by else match.active_side


def can_double(match):
    return (
        match.status == 'active'
        and match.phase == 'awaiting_roll'
        and not match.is_crawford
        and match.cube_owner in (None, match.active_side)
        and getattr(match, f'score_{match.active_side}') + match.cube_value < match.target_score
    )


def _wallet(match, user_id):
    wallet = Wallet.objects.select_for_update().filter(currency_id=match.currency_id, owner_id=user_id).first()
    if wallet is None:
        raise ValidationError('A TNB wallet is required for a staked match.')
    return wallet


def _transfer(match, user_id, amount, action):
    if not amount:
        return
    wallet = _wallet(match, user_id)
    if wallet.balance + amount < 0:
        raise ValidationError('Insufficient TNB balance for this stake.')
    BackgammonLedgerEntry.objects.create(match=match, wallet=wallet, amount=amount, action=action)
    wallet.change_balance(amount, should_stream=True)


def _record(match, event_type, payload=None, *, initial=False):
    if not initial:
        match.version += 1
    match.save()
    BackgammonEvent.objects.create(match=match, version=match.version, event_type=event_type, payload=payload or {})


def roll_dice():
    return [randbelow(6) + 1, randbelow(6) + 1]


def _start_game(match):
    match.game_number += 1
    match.board = initial_board()
    match.cube_value = 1
    match.cube_owner = None
    match.double_offered_by = None
    match.is_crawford = not match.crawford_used and max(match.score_white, match.score_black) == match.target_score - 1
    if match.is_crawford:
        match.crawford_used = True
    # Opening roll: one die per side, ties rerolled. Both dice form the first turn.
    dice = roll_dice()
    while dice[0] == dice[1]:
        dice = roll_dice()
    match.dice = dice
    match.active_side = 'white' if dice[0] > dice[1] else 'black'
    match.status = 'active'
    match.next_game_at = None
    match.phase = 'moving'
    match.turn_started_at = timezone.now()


def create_match(
    *,
    user,
    mode,
    opponent=None,
    difficulty='normal',
    stake_amount=0,
    target_score=3,
    time_limit_seconds=900,
    rematch_of=None,
    request_id=None,
    guest_session=None,
):
    # Serialize new challenges from a user so rapid retries cannot bypass the cap.
    owner = match_owner(user, guest_session, 'white')
    if guest_session and (mode != 'computer' or stake_amount or opponent):
        raise PermissionDenied('Guests can only play free computer games.')
    lock_match_owner(user, guest_session)
    request_id = request_id or uuid.uuid4()
    existing = BackgammonMatch.objects.filter(**owner, request_id=request_id).first()
    if existing:
        same_request = (
            existing.mode == mode
            and existing.black_id == (opponent.id if opponent else None)
            and existing.difficulty == difficulty
            and existing.stake_amount == stake_amount
            and existing.target_score == target_score
            and existing.time_limit_seconds == time_limit_seconds
            and existing.rematch_of_id == (rematch_of.id if rematch_of else None)
        )
        if not same_request:
            raise StateConflict('This request ID was already used with different match settings.')
        return existing
    if BackgammonMatch.objects.filter(**owner, status__in=UNFINISHED).count() >= 10:
        raise ValidationError('Finish or cancel an existing match before creating another (maximum 10).')
    currency = None
    if stake_amount:
        currency = Currency.objects.filter(ticker=settings.DEFAULT_CURRENCY_TICKER).first()
        if currency is None:
            raise ValidationError('TNB is not configured yet.')
    match = BackgammonMatch.objects.create(
        white=user,
        guest_session=guest_session,
        black=opponent,
        mode=mode,
        difficulty=difficulty,
        currency=currency,
        stake_amount=stake_amount,
        prize_pool_total=stake_amount,
        target_score=target_score,
        time_limit_seconds=time_limit_seconds,
        clock_white_ms=time_limit_seconds * 1000,
        clock_black_ms=time_limit_seconds * 1000,
        expires_at=timezone.now() + timedelta(minutes=5),
        rematch_of=rematch_of,
        request_id=request_id,
    )
    _transfer(match, user.id if user else None, -stake_amount, 'stake')
    if mode == 'computer':
        _start_game(match)
    _record(match, 'created', {'dice': match.dice}, initial=True)
    if mode == 'human':
        from .notifications import notify_challenge

        notify_challenge(match)
    queue_computer(match)
    return match


def expire_match(match):
    if match.status != 'pending' or match.expires_at > timezone.now():
        return False
    close_challenge(match, 'expired')
    return True


def close_challenge(match, status):
    if match.status != 'pending':
        raise StateConflict('This challenge is no longer pending.')
    if not match.settled:
        _transfer(match, match.white_id, match.prize_pool_total, 'refund')
        match.settled = True
    match.status = status
    match.phase = 'finished'
    match.finished_at = timezone.now()
    _record(match, status)


def accept_match(match):
    _transfer(match, match.black_id, -match.stake_amount, 'stake')
    match.prize_pool_total += match.stake_amount
    _start_game(match)
    _record(match, 'accepted', {'dice': match.dice})


def finish_match(match, winning_side, reason):
    if match.settled:
        raise StateConflict('The match has already settled.')
    if match.mode == 'computer':
        from thenewboston.game_rewards.services import settle_computer_reward

        match.computer_reward = settle_computer_reward(
            game='backgammon',
            match_id=match.id,
            user_id=match.white_id,
            won=winning_side == 'white' and reason in {'single', 'gammon', 'backgammon', 'double_declined'},
        )
    winning_user_id = match.white_id if winning_side == 'white' else match.black_id
    _transfer(match, winning_user_id, match.prize_pool_total, 'payout')
    match.settled = True
    match.winner = winning_side
    match.status = 'finished'
    match.phase = 'finished'
    match.result_reason = reason
    if reason in {'resignation', 'timeout'}:
        match.game_winner = winning_side
        match.result_points = 0
    match.double_offered_by = None
    match.finished_at = timezone.now()
    match.turn_started_at = None
    match.next_game_at = None


def apply_clock(match):
    side = clock_side(match)
    if side is None:
        return False
    now = timezone.now()
    elapsed = max(0, int((now - match.turn_started_at).total_seconds() * 1000))
    field = f'clock_{side}_ms'
    remaining = max(0, getattr(match, field) - elapsed)
    setattr(match, field, remaining)
    match.turn_started_at = now
    if remaining:
        return False
    finish_match(match, opponent(side), 'timeout')
    _record(match, 'timeout', {'side': side})
    return True


def _finish_game(match, winning_side, points, reason):
    field = f'score_{winning_side}'
    setattr(match, field, getattr(match, field) + points)
    match.game_winner = winning_side
    match.result_points = points
    match.result_reason = reason
    match.double_offered_by = None
    match.turn_started_at = None
    if getattr(match, field) >= match.target_score:
        finish_match(match, winning_side, reason)
    else:
        match.status = 'between_games'
        match.phase = 'game_over'
        match.next_game_at = timezone.now() + timedelta(seconds=30)


def start_next_game(match):
    if match.status != 'between_games':
        raise StateConflict('The next game is not ready.')
    _start_game(match)
    _record(match, 'next_game', {'dice': match.dice})


def make_move(match, moves):
    if match.phase != 'moving':
        raise StateConflict('Roll the dice before moving.')
    try:
        match.board = apply_turn(match.board, match.active_side, match.dice, moves)
    except ValueError as error:
        raise ValidationError(str(error)) from error
    payload = {'side': match.active_side, 'dice': match.dice, 'moves': moves}
    if winning_side := winner(match.board):
        multiplier = win_points(match.board, winning_side)
        _finish_game(
            match, winning_side, multiplier * match.cube_value, ['single', 'gammon', 'backgammon'][multiplier - 1]
        )
    else:
        match.active_side = opponent(match.active_side)
        match.phase = 'awaiting_roll'
        match.dice = []
        match.turn_started_at = timezone.now()
    _record(match, 'move', payload)


def offer_double(match):
    if not can_double(match):
        raise StateConflict('The doubling cube is not available now.')
    match.double_offered_by = match.active_side
    match.phase = 'doubling'
    match.turn_started_at = timezone.now()
    _record(match, 'double', {'side': match.active_side, 'value': match.cube_value * 2})


def respond_double(match, accept):
    offering_side = match.double_offered_by
    if not offering_side:
        raise StateConflict('There is no double to respond to.')
    if accept:
        match.cube_value *= 2
        match.cube_owner = opponent(offering_side)
        match.double_offered_by = None
        match.phase = 'awaiting_roll'
        match.turn_started_at = timezone.now()
    else:
        _finish_game(match, offering_side, match.cube_value, 'double_declined')
    _record(match, 'double_response', {'accept': accept, 'side': opponent(offering_side)})


def perform_action(match, user, action, data, guest_session=None):
    side = player_side(match, user.id if user else None, guest_session)
    if side is None:
        raise PermissionDenied('Only the players can change this match.')
    if data['expected_version'] != match.version:
        raise StateConflict()
    if expire_match(match):
        return match
    if action in {'accept', 'decline', 'cancel'}:
        if match.status != 'pending':
            raise StateConflict('This challenge is no longer pending.')
        required_side = 'white' if action == 'cancel' else 'black'
        if side != required_side:
            raise PermissionDenied('Only the challenger can cancel; only the opponent can accept or decline.')
        if action == 'accept':
            accept_match(match)
        else:
            close_challenge(match, 'cancelled' if action == 'cancel' else 'declined')
    elif action == 'rematch':
        if match.status != 'finished':
            raise StateConflict('Finish the current match before requesting a rematch.')
        existing = BackgammonMatch.objects.filter(rematch_of=match, status__in=UNFINISHED).first()
        if existing:
            return existing
        other = match.black if side == 'white' else match.white
        return create_match(
            user=user,
            mode=match.mode,
            opponent=other,
            difficulty=match.difficulty,
            stake_amount=match.stake_amount,
            target_score=match.target_score,
            time_limit_seconds=match.time_limit_seconds,
            rematch_of=match,
            guest_session=guest_session,
        )
    elif action == 'next_game':
        start_next_game(match)
    else:
        if match.status not in {'active', 'between_games'}:
            raise StateConflict('This match is not active.')
        if apply_clock(match):
            return match
        if action == 'resign':
            finish_match(match, opponent(side), 'resignation')
            _record(match, 'resign', {'side': side})
        elif action == 'respond_double':
            if match.phase != 'doubling' or side != opponent(match.double_offered_by):
                raise PermissionDenied('Only the player offered the double can respond.')
            respond_double(match, data['accept'])
        else:
            if match.status != 'active' or side != match.active_side or match.phase == 'doubling':
                raise PermissionDenied('Wait for your turn.')
            if action == 'roll':
                if match.phase != 'awaiting_roll':
                    raise StateConflict('The dice have already been rolled.')
                match.dice = roll_dice()
                match.phase = 'moving'
                _record(match, 'roll', {'side': side, 'dice': match.dice})
            elif action == 'move':
                make_move(match, data['moves'])
            elif action == 'double':
                offer_double(match)
            else:
                raise ValidationError('Unknown match action.')
    queue_computer(match)
    return match


def computer_ready(match):
    return match.mode == 'computer' and match.status == 'active' and clock_side(match) == 'black'


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
            # The periodic sweep retries delivery from persisted match state.
            logger.exception('Could not enqueue backgammon computer turn for match %s', match_id)

    apply_on_commit(enqueue)


@transaction.atomic
def run_computer(match_id, expected_version):
    from .ai import choose_turn, pip_count

    match = BackgammonMatch.objects.select_for_update().filter(pk=match_id).first()
    if match is None or match.version != expected_version or not computer_ready(match):
        return
    if apply_clock(match):
        return
    if match.phase == 'doubling':
        # A simple practice opponent evaluates the race without seeing future dice.
        accept = pip_count(match.board, 'black') <= pip_count(match.board, 'white') * 1.35 + 12
        respond_double(match, accept)
        return
    if can_double(match) and match.difficulty != 'easy':
        if pip_count(match.board, 'black') < pip_count(match.board, 'white') * 0.65:
            offer_double(match)
            return
    if match.phase == 'awaiting_roll':
        match.dice = roll_dice()
        match.phase = 'moving'
    moves = choose_turn(match.board, 'black', match.dice, match.difficulty)
    if not apply_clock(match):
        make_move(match, moves)
