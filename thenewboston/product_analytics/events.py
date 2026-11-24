import logging
import uuid

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .context import request_context
from .models import AnalyticsEvent, GameInvitationContext, GameParticipant

logger = logging.getLogger(__name__)

# Model, first player field/side, second player field/side. Reversi selects colors at creation.
MATCHES = {
    'backgammon': ('BackgammonMatch', 'white', 'white', 'black', 'black'),
    'battleship': ('BattleshipMatch', 'host', 'host', 'guest', 'guest'),
    'checkers': ('CheckersMatch', 'white', 'white', 'black', 'black'),
    'connect_five': ('ConnectFiveMatch', 'player_a', 'a', 'player_b', 'b'),
    'dots_and_boxes': ('DotsAndBoxesMatch', 'blue', 'blue', 'red', 'red'),
    'hex': ('HexMatch', 'red', 'red', 'blue', 'blue'),
    'mancala': ('MancalaMatch', 'host', 'host', 'guest', 'guest'),
    'reversi': ('ReversiMatch', 'host', None, 'guest', None),
}


def safely_record(callback, *args, **kwargs):
    if not settings.POSTHOG_ENABLED:
        return
    try:
        # A telemetry write error must not mark the surrounding game/payment transaction broken.
        with transaction.atomic():
            callback(*args, **kwargs)
    except Exception:
        logger.exception('Could not persist product analytics event')


def enqueue_event(key, event, identity, properties, occurred_at=None):
    if not identity.get('enabled') or not identity.get('distinct_id'):
        return
    properties = {
        **properties,
        'analytics_version': 1,
        'event_source': 'server',
        'internal_traffic': identity['internal_traffic'],
        'auth_state': 'authenticated' if identity.get('user_id') else 'guest',
        **identity.get('attribution', {}),
    }
    if identity.get('session_id'):
        properties['$session_id'] = identity['session_id']
    if identity.get('user_id'):
        user_id = identity['user_id']
        user = apps.get_model('users', 'User').objects.filter(pk=user_id).only('username', 'is_staff').first()
        properties['user_id'] = user_id
        properties['profile_url'] = f'https://thenewboston.net/profile/{user_id}'
        if user:
            properties['internal_traffic'] = properties['internal_traffic'] or user.is_staff
            properties['$set'] = {
                'user_id': user_id,
                'username': user.username,
                'profile_url': properties['profile_url'],
            }
    else:
        properties['$process_person_profile'] = False
    AnalyticsEvent.objects.get_or_create(
        key=key,
        defaults={
            'id': uuid.uuid5(uuid.NAMESPACE_URL, f'thenewboston:analytics:{key}'),
            'event': event,
            'distinct_id': identity['distinct_id'],
            'properties': properties,
            'occurred_at': occurred_at or timezone.now(),
        },
    )


def user_identity(user_id, *, participant=None, signup=False):
    context = request_context()
    identity = {
        'enabled': True,
        'distinct_id': str(user_id),
        'user_id': user_id,
        'session_id': '',
        'internal_traffic': False,
        'attribution': {},
    }
    if participant is not None:
        identity.update(participant_identity(participant))
    if context and (context['user_id'] == user_id or signup):
        identity.update(
            enabled=not context['opt_out'],
            session_id=context['session_id'],
            internal_traffic=identity['internal_traffic'] or context['internal_traffic'],
            attribution=context['attribution'],
        )
    return identity


def participant_identity(participant):
    return {
        key: getattr(participant, key)
        for key in ('enabled', 'distinct_id', 'user_id', 'session_id', 'internal_traffic', 'attribution')
    }


def participant_sides(game, match):
    _, first_field, first_side, second_field, second_side = MATCHES[game]
    if game == 'reversi':
        first_side = match.host_side
        second_side = 'white' if first_side == 'black' else 'black'
    sides = [(first_field, first_side)]
    if match.mode == 'human':
        sides.append((second_field, second_side))
    return sides


def update_participants(game, match, *, created):
    context = request_context()
    participants = []
    for field, side in participant_sides(game, match):
        user_id = getattr(match, f'{field}_id')
        participant = GameParticipant.objects.filter(game=game, match_id=match.pk, side=side).first()
        if participant is None:
            if not created:
                continue
            participant = GameParticipant(
                game=game,
                match_id=match.pk,
                side=side,
                user_id=user_id,
                guest_session_id=match.guest_session_id,
            )
            if game == 'connect_five' and match.challenge_id:
                invitation = GameInvitationContext.objects.filter(challenge_id=match.challenge_id).first()
                if invitation and invitation.identity.get('user_id') == user_id:
                    for key, value in invitation.identity.items():
                        setattr(participant, key, value)
        # A spectator or the other player cannot opt this participant in or replace their identity.
        own_request = context and (
            (user_id is not None and context['user_id'] == user_id)
            or (
                user_id is None
                and context['user_id'] is None
                and match.guest_session_id
                and context['guest_session_id'] == match.guest_session_id
            )
        )
        if own_request:
            participant.enabled = not context['opt_out'] and bool(user_id or context['distinct_id'])
            # A browser reset must not split the original guest play across unrelated identities.
            if user_id or not participant.started_at:
                participant.distinct_id = str(user_id) if user_id else context['distinct_id']
                participant.session_id = context['session_id']
                participant.attribution = context['attribution']
            participant.internal_traffic = participant.internal_traffic or context['internal_traffic']
        participant.save()
        participants.append(participant)
    return participants


def match_properties(game, match):
    return {
        'game': game,
        'match_id': match.pk,
        'match_key': f'{game}:{match.pk}',
        'mode': match.mode,
        'difficulty': match.difficulty if match.mode == 'computer' else None,
        'time_limit_seconds': match.time_limit_seconds,
        'stake_amount': getattr(match, 'stake_amount', 0),
    }


def record_match(game, match, *, created, previous_status, status_written=True):
    participants = update_participants(game, match, created=created)
    started = status_written and match.status == 'active' and (created or previous_status == 'pending')
    completed = (
        status_written and str(match.status).startswith('finished') and previous_status in {'active', 'between_games'}
    )
    properties = match_properties(game, match)
    for participant in participants:
        identity = participant_identity(participant)
        if started and participant.started_at is None:
            participant.started_at = timezone.now()
            enqueue_event(
                f'game_started:{game}:{match.pk}:{participant.side}',
                'game_started',
                identity,
                properties,
                participant.started_at,
            )
        if completed and participant.started_at and participant.completed_at is None:
            participant.completed_at = match.finished_at or timezone.now()
            winner = match.winner_side if game == 'connect_five' and match.mode == 'computer' else match.winner
            if game == 'connect_five' and match.mode == 'human':
                outcome = (
                    'draw' if not match.winner_id else ('win' if match.winner_id == participant.user_id else 'loss')
                )
            else:
                outcome = 'draw' if winner is None else ('win' if winner == participant.side else 'loss')
            receipt = match.computer_reward or {}
            enqueue_event(
                f'game_completed:{game}:{match.pk}:{participant.side}',
                'game_completed',
                identity,
                {
                    **properties,
                    'outcome': outcome,
                    'finish_reason': getattr(match, 'result_reason', '') or str(match.status),
                    'elapsed_seconds': max(0, (participant.completed_at - participant.started_at).total_seconds()),
                    'reward_status': receipt.get('status'),
                    'reward_amount': receipt.get('amount', 0) if receipt.get('status') == 'paid' else 0,
                    'guest_reward_offer': receipt.get('status') == 'guest',
                },
                participant.completed_at,
            )
        participant.save(update_fields=['started_at', 'engaged_at', 'completed_at'])


def record_engagement(game, event):
    # Existing game event rows are created only after a validated action succeeds.
    if event.event_type not in {'move', 'placed', 'shot', 'swap', 'roll', 'double', 'double_response'}:
        return
    context = request_context()
    if context is None:
        return
    match = event.match
    side = event.payload.get('side')
    if game == 'connect_five' and match.mode == 'human':
        side = 'a' if event.actor_id == match.player_a_id else 'b'
    participant = GameParticipant.objects.filter(game=game, match_id=match.pk, side=side).first()
    if participant is None or participant.engaged_at or not participant.started_at:
        return
    own_request = (participant.user_id is not None and participant.user_id == context['user_id']) or (
        participant.user_id is None
        and participant.guest_session_id is not None
        and participant.guest_session_id == context['guest_session_id']
    )
    if not own_request:
        return
    # First-action wins must retain ordered start -> engagement -> completion timestamps.
    participant.engaged_at = max(participant.started_at, context['received_at'] or event.created_date)
    identity = participant_identity(participant)
    identity['enabled'] = identity['enabled'] and not context['opt_out']
    enqueue_event(
        f'game_engaged:{game}:{match.pk}:{side}',
        'game_engaged',
        identity,
        {**match_properties(game, match), 'first_action': event.event_type},
        participant.engaged_at,
    )
    participant.save(update_fields=['engaged_at'])


def record_invitation(challenge):
    context = request_context()
    if context and context['user_id'] == challenge.challenger_id:
        GameInvitationContext.objects.update_or_create(
            challenge_id=challenge.pk,
            defaults={'identity': user_identity(challenge.challenger_id)},
        )


def record_privacy_choice():
    context = request_context()
    if not context or not context['opt_out']:
        return
    if context['user_id'] is not None:
        GameParticipant.objects.filter(user_id=context['user_id'], enabled=True).update(enabled=False)
        # A pending Connect Five invitation retains the challenger's current choice on acceptance.
        for invitation in GameInvitationContext.objects.filter(
            identity__user_id=context['user_id'], identity__enabled=True
        ):
            invitation.identity['enabled'] = False
            invitation.save(update_fields=['identity'])
    elif context['guest_session_id']:
        GameParticipant.objects.filter(guest_session_id=context['guest_session_id'], enabled=True).update(enabled=False)


def record_reward(decision):
    participant = GameParticipant.objects.filter(
        game=decision.game,
        match_id=decision.match_id,
        user_id=decision.user_id,
    ).first()
    identity = user_identity(decision.user_id, participant=participant)
    properties = {
        'game': decision.game,
        'match_id': decision.match_id,
        'match_key': f'{decision.game}:{decision.match_id}',
        'reward_id': decision.pk,
        'recipient_id': decision.user_id,
        'reward_status': decision.status,
        'amount': decision.amount,
        'currency': 'TNB',
    }
    enqueue_event(
        f'game_reward_decided:{decision.pk}', 'game_reward_decided', identity, properties, decision.created_date
    )
    if decision.status == 'paid':
        enqueue_event(
            f'game_reward_paid:{decision.pk}', 'game_reward_paid', identity, properties, decision.created_date
        )


def record_deposit(deposit):
    enqueue_event(
        f'game_fund_deposited:{deposit.pk}',
        'game_fund_deposited',
        user_identity(deposit.donor_id),
        {'deposit_id': deposit.pk, 'donor_id': deposit.donor_id, 'amount': deposit.amount, 'currency': 'TNB'},
        deposit.created_date,
    )


def record_signup(user):
    identity = user_identity(user.pk, signup=True)
    context = request_context()
    if context and context['distinct_id'] and not context['opt_out']:
        # Standard identify payload links the pre-signup browser history even if the response is lost.
        enqueue_event(
            f'signup_identity:{user.pk}',
            '$identify',
            identity,
            {'$anon_distinct_id': context['distinct_id']},
        )
    enqueue_event(f'signup_completed:{user.pk}', 'signup_completed', identity, {'signup_method': 'password'})
