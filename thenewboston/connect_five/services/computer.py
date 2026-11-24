"""Free computer matches, isolated from human escrow and ranked statistics."""

import logging
import uuid
from secrets import randbelow

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from thenewboston.general.utils.database import apply_on_commit

from .clocks import apply_elapsed_time, switch_turn
from .computer_ai import INVENTORY_FIELDS, choose_move
from .rules import apply_move, check_win, is_board_full
from ..enums import MatchEventType, MatchStatus
from ..exceptions import ConflictError, GoneError
from ..models import ConnectFiveMatch, ConnectFiveMatchEvent, ConnectFiveMatchPlayer

logger = logging.getLogger(__name__)
FREE_SPECIALS = 2


def create_computer_match(*, user, request_id, difficulty='normal', time_limit_seconds=900, rematch_of=None):
    previous = None
    if rematch_of:
        previous = get_object_or_404(
            ConnectFiveMatch.objects.select_for_update(of=('self',)),
            pk=rematch_of,
            mode='computer',
            player_a=user,
        )
        if previous.status == MatchStatus.ACTIVE:
            raise ConflictError('Finish the current match before playing again.')
        if previous.difficulty != difficulty or previous.time_limit_seconds != time_limit_seconds:
            raise ValidationError('A rematch must use the same difficulty and clock.')
    # NO KEY UPDATE allows foreign-key checks in simultaneous matches without deadlocks.
    get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
    existing = ConnectFiveMatch.objects.filter(mode='computer', player_a=user, request_id=request_id).first()
    if existing:
        if (
            existing.difficulty != difficulty
            or existing.time_limit_seconds != time_limit_seconds
            or existing.computer_rematch_of_id != rematch_of
        ):
            raise ConflictError('This request ID was already used with different match settings.')
        return existing
    if previous:
        active_rematch = previous.computer_rematches.filter(status=MatchStatus.ACTIVE).first()
        if active_rematch:
            return active_rematch
    if ConnectFiveMatch.objects.filter(mode='computer', player_a=user, status=MatchStatus.ACTIVE).count() >= 10:
        raise ValidationError('Finish an existing computer game before creating another (maximum 10).')
    match = ConnectFiveMatch.objects.create(
        mode='computer',
        difficulty=difficulty,
        request_id=request_id,
        player_a=user,
        player_b=None,
        challenge=None,
        active_player=user if randbelow(2) == 0 else None,
        time_limit_seconds=time_limit_seconds,
        clock_a_remaining_ms=time_limit_seconds * 1000,
        clock_b_remaining_ms=time_limit_seconds * 1000,
        prize_pool_total=0,
        max_spend_amount=0,
        computer_rematch_of=previous,
    )
    for player in (user, None):
        ConnectFiveMatchPlayer.objects.create(
            match=match,
            user=player,
            inventory_h2=FREE_SPECIALS,
            inventory_v2=FREE_SPECIALS,
            inventory_bomb=FREE_SPECIALS,
        )
    queue_computer_turn(match)
    return match


def finish_computer_match(*, match, winner_side, status):
    if match.mode != 'computer':
        raise ValueError('Computer settlement cannot be used for human matches.')
    if match.status != MatchStatus.ACTIVE:
        return
    from thenewboston.game_rewards.services import settle_computer_reward

    match.status = status
    match.winner_side = winner_side
    match.winner_id = match.player_a_id if winner_side == 'a' else None
    match.finished_at = timezone.now()
    match.active_player = None
    match.version += 1
    match.computer_reward = settle_computer_reward(
        game='connect_five',
        match_id=match.id,
        user_id=match.player_a_id,
        won=winner_side == 'a' and status == MatchStatus.FINISHED_CONNECT5,
    )
    match.save()
    ConnectFiveMatchEvent.objects.create(
        match=match,
        actor_id=match.winner_id,
        event_type=MatchEventType.SETTLEMENT,
        payload={
            'mode': 'computer',
            'reason': status,
            'winner_side': winner_side,
            'version': match.version,
            'computer_reward': match.computer_reward,
        },
    )


def expire_computer_match(match):
    if match.mode != 'computer' or match.status != MatchStatus.ACTIVE:
        return False
    side = 'a' if match.active_player_id == match.player_a_id else 'b'
    elapsed = max(0, int((timezone.now() - match.turn_started_at).total_seconds() * 1000))
    if elapsed < getattr(match, f'clock_{side}_remaining_ms'):
        return False
    setattr(match, f'clock_{side}_remaining_ms', 0)
    finish_computer_match(match=match, winner_side='b' if side == 'a' else 'a', status=MatchStatus.FINISHED_TIMEOUT)
    return True


def apply_computer_move(match, *, side, move):
    if expire_computer_match(match):
        return
    user_id = match.player_a_id if side == 'a' else None
    if match.active_player_id != user_id:
        raise PermissionDenied('It is not your turn.')
    player = ConnectFiveMatchPlayer.objects.select_for_update().get(match=match, user_id=user_id)
    inventory_field = INVENTORY_FIELDS.get(move['move_type'])
    if inventory_field and getattr(player, inventory_field) <= 0:
        raise ValidationError('No free inventory remains for this special.')
    value = 1 if side == 'a' else 2
    board, placed, removed = apply_move(board_state=match.board_state, player_value=value, **move)
    # Check again at mutation time so an expired clock cannot win with a late move.
    remaining, now = apply_elapsed_time(match)
    if remaining <= 0:
        finish_computer_match(match=match, winner_side='b' if side == 'a' else 'a', status=MatchStatus.FINISHED_TIMEOUT)
        return
    match.board_state = board
    if inventory_field:
        setattr(player, inventory_field, getattr(player, inventory_field) - 1)
        player.save(update_fields=[inventory_field, 'modified_date'])
    ConnectFiveMatchEvent.objects.create(
        match=match,
        actor_id=user_id,
        event_type=MatchEventType.MOVE,
        payload={
            'mode': 'computer',
            'side': side,
            'move_type': move['move_type'],
            'placed': placed,
            'removed': removed,
            'version': match.version + 1,
        },
    )
    if placed and check_win(board_state=board, player_value=value, positions=placed):
        finish_computer_match(match=match, winner_side=side, status=MatchStatus.FINISHED_CONNECT5)
    elif is_board_full(board):
        # Retain Connect 5's established tie-break: the player who moved second wins.
        winner_side = side if match.turn_number % 2 == 0 else ('b' if side == 'a' else 'a')
        finish_computer_match(match=match, winner_side=winner_side, status=MatchStatus.FINISHED_FULL_BOARD)
    else:
        switch_turn(match, now=now)
        match.version += 1
        match.save()
    queue_computer_turn(match)


def perform_computer_action(match, *, user, action, data):
    if match.player_a_id != user.id:
        raise PermissionDenied('Only the player can change this computer match.')
    if data['expected_version'] != match.version:
        raise ConflictError('The match changed. Refresh it before trying again.')
    if match.status != MatchStatus.ACTIVE:
        raise GoneError('Match is no longer active.')
    if expire_computer_match(match):
        return
    if action == 'resign':
        finish_computer_match(match=match, winner_side='b', status=MatchStatus.FINISHED_RESIGN)
    elif action == 'move':
        apply_computer_move(match, side='a', move={key: data[key] for key in ('move_type', 'x', 'y')})
    else:
        raise ValidationError('Unknown computer match action.')


def computer_ready(match):
    return match.mode == 'computer' and match.status == MatchStatus.ACTIVE and match.active_player_id is None


def queue_computer_turn(match):
    if not computer_ready(match):
        return
    from ..tasks import play_connect_five_computer_turn

    match_id, version = match.id, match.version

    def enqueue():
        try:
            play_connect_five_computer_turn.delay(match_id, version)
        except Exception:
            # The existing periodic timeout sweep retries from persisted state.
            logger.exception('Could not queue Connect 5 computer turn for match %s', match_id)

    apply_on_commit(enqueue)


@transaction.atomic
def run_computer_turn(match_id, expected_version):
    match = ConnectFiveMatch.objects.select_for_update().filter(pk=match_id).first()
    if match is None or match.version != expected_version or not computer_ready(match) or expire_computer_match(match):
        return
    players = {player.user_id: player for player in match.players.all()}
    inventories = [
        {field: getattr(players[user_id], field) for field in INVENTORY_FIELDS.values()}
        for user_id in (None, match.player_a_id)
    ]
    move = choose_move(match.board_state, *inventories, difficulty=match.difficulty)
    apply_computer_move(match, side='b', move=move)


def rematch_computer(match, user):
    if match.player_a_id != user.id:
        raise PermissionDenied('Only the player can rematch the computer.')
    return create_computer_match(
        user=user,
        request_id=uuid.uuid4(),
        difficulty=match.difficulty,
        time_limit_seconds=match.time_limit_seconds,
        rematch_of=match.id,
    )
