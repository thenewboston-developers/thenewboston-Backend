from contextlib import ExitStack, contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.apps import apps
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, transaction
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.game_rewards.services import contribute, settle_computer_reward
from thenewboston.product_analytics.context import AnalyticsContextMiddleware, current_request, request_context
from thenewboston.product_analytics.events import MATCHES, record_signup, safely_record
from thenewboston.product_analytics.models import AnalyticsEvent, GameParticipant
from thenewboston.product_analytics.tasks import deliver_product_analytics

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def analytics_enabled(settings):
    settings.POSTHOG_ENABLED = True
    cache.clear()
    with ExitStack() as stack:
        for game in MATCHES:
            path = (
                'thenewboston.connect_five.services.computer.queue_computer_turn'
                if game == 'connect_five'
                else f'thenewboston.{game}.services.queue_computer'
            )
            stack.enter_context(patch(path))
        stack.enter_context(patch('thenewboston.connect_five.services.computer.randbelow', return_value=0))
        yield


def tracked_client(user=None, opt_out=False):
    client = APIClient()
    anonymous_id, session_id = str(uuid4()), str(uuid4())
    headers = {
        'HTTP_X_POSTHOG_DISTINCT_ID': str(user.pk) if user else anonymous_id,
        'HTTP_X_POSTHOG_SESSION_ID': session_id,
    }
    if opt_out:
        headers['HTTP_X_POSTHOG_OPT_OUT'] = '1'
    if user:
        client.force_authenticate(user)
    else:
        response = client.post('/api/guest-games/session', {}, format='json')
        assert response.status_code == 201
        headers['HTTP_X_GUEST_TOKEN'] = response.data['token']
    client.credentials(**headers)
    return client, anonymous_id, session_id


def create_match(client, game, **extra):
    path = f'/api/{game.replace("_", "-")}/matches'
    data = {'request_id': str(uuid4()), **extra}
    if game == 'connect_five':
        path += '/computer'
    else:
        data.setdefault('mode', 'computer')
    response = client.post(path, data, format='json')
    assert response.status_code == 201, response.data
    model = apps.get_model(game, MATCHES[game][0])
    return model.objects.get(pk=response.data['id']), data


@contextmanager
def request_for(user=None, **headers):
    request = RequestFactory().post('/api/test', **headers)
    request.user = user or AnonymousUser()
    token = current_request.set(request)
    try:
        yield request
    finally:
        current_request.reset(token)


@pytest.mark.parametrize('game', MATCHES)
@pytest.mark.parametrize('authenticated', [False, True])
def test_start_and_completion_are_once_per_actual_participant(game, authenticated, bucky):
    client, anonymous_id, session_id = tracked_client(bucky if authenticated else None)
    match, payload = create_match(client, game)
    started = AnalyticsEvent.objects.get(event='game_started')
    assert started.distinct_id == (str(bucky.pk) if authenticated else anonymous_id)
    assert started.properties['$session_id'] == session_id
    assert started.properties['auth_state'] == ('authenticated' if authenticated else 'guest')
    assert started.properties['game'] == game
    assert started.properties['mode'] == 'computer'
    assert 'guest_session_id' not in started.properties
    assert 'password' not in started.properties and 'email' not in started.properties
    _, _ = create_match(client, game, **payload)
    path = f'/api/{game.replace("_", "-")}/matches/{match.pk}'
    assert client.get(path).status_code == 200
    response = client.post(path + '/resign', {'expected_version': match.version}, format='json')
    assert response.status_code == 200, response.data
    assert client.get(path).status_code == 200
    match.refresh_from_db()
    match.save()
    assert AnalyticsEvent.objects.filter(event='game_started').count() == 1
    completed = AnalyticsEvent.objects.get(event='game_completed')
    assert completed.distinct_id == started.distinct_id
    assert completed.properties['outcome'] == 'loss'
    assert completed.properties['reward_amount'] == 0
    assert completed.properties['elapsed_seconds'] >= 0
    assert not AnalyticsEvent.objects.filter(event='game_reward_paid').exists()


@pytest.mark.parametrize('authenticated', [False, True])
def test_opt_out_survives_background_completion(authenticated, bucky):
    client, _, _ = tracked_client(bucky if authenticated else None, opt_out=True)
    match, _ = create_match(client, 'checkers')
    participant = GameParticipant.objects.get()
    assert not participant.enabled
    from thenewboston.checkers.services import finish_match

    with transaction.atomic():
        finish_match(match, 'black', 'no_moves')
        match.save()
    assert not AnalyticsEvent.objects.exists()


def test_guest_win_is_offer_not_paid_and_snapshot_survives_guest_cleanup(tnb_currency):
    GameFund.objects.update_or_create(pk=1, defaults={'balance': 100, 'total_deposited': 100, 'currency': tnb_currency})
    client, anonymous_id, _ = tracked_client()
    match, _ = create_match(client, 'checkers')
    match.board = [0] * 64
    match.board[42], match.board[35] = 1, -1
    match.save()
    response = client.post(
        f'/api/checkers/matches/{match.pk}/move',
        {'expected_version': match.version, 'path': [42, 28]},
        format='json',
    )
    assert response.status_code == 200, response.data
    completed = AnalyticsEvent.objects.get(event='game_completed')
    assert completed.distinct_id == anonymous_id
    assert completed.properties['outcome'] == 'win'
    assert completed.properties['guest_reward_offer']
    assert completed.properties['reward_amount'] == 0
    engaged = AnalyticsEvent.objects.get(event='game_engaged')
    assert AnalyticsEvent.objects.get(event='game_started').occurred_at <= engaged.occurred_at <= completed.occurred_at
    assert not AnalyticsEvent.objects.filter(event='game_reward_paid').exists()
    assert not GameRewardDecision.objects.exists()
    match.guest_session.delete()
    assert AnalyticsEvent.objects.filter(pk=completed.pk).exists()


def test_deposit_and_reward_retry_are_once_and_rollback_discards_outbox(bucky_tnb_wallet, dmitry_tnb_wallet):
    client, _, _ = tracked_client(bucky_tnb_wallet.owner)
    data = {'amount': 20, 'request_id': str(uuid4())}
    for _ in range(2):
        assert client.post('/api/game-fund/deposits', data).status_code == 201
    deposit = AnalyticsEvent.objects.get(event='game_fund_deposited')
    assert deposit.properties['amount'] == 20
    assert deposit.properties['donor_id'] == bucky_tnb_wallet.owner_id
    assert deposit.properties['$set']['username'] == bucky_tnb_wallet.owner.username
    for _ in range(2):
        settle_computer_reward(game='checkers', match_id=100, user_id=dmitry_tnb_wallet.owner_id, won=True)
    paid = AnalyticsEvent.objects.get(event='game_reward_paid')
    assert paid.properties['amount'] == 10
    assert paid.properties['recipient_id'] == dmitry_tnb_wallet.owner_id
    with pytest.raises(RuntimeError), transaction.atomic():
        settle_computer_reward(game='checkers', match_id=101, user_id=dmitry_tnb_wallet.owner_id, won=True)
        raise RuntimeError('rollback')
    assert AnalyticsEvent.objects.filter(event='game_reward_paid').count() == 1
    assert GameFund.objects.get().balance == 10


def test_analytics_write_failure_does_not_break_financial_transaction(bucky_tnb_wallet):
    with patch.object(AnalyticsEvent.objects, 'get_or_create', side_effect=DatabaseError('outbox unavailable')):
        contribute(user=bucky_tnb_wallet.owner, amount=20, request_id=uuid4())
    assert GameFund.objects.get().balance == 20
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 980


def test_human_invitation_does_not_start_until_accepted_and_does_not_share_consent(bucky, dmitry):
    inviter, _, inviter_session = tracked_client(bucky, opt_out=True)
    invitee, _, invitee_session = tracked_client(dmitry)
    match, _ = create_match(inviter, 'checkers', mode='human', opponent_id=dmitry.pk)
    assert not AnalyticsEvent.objects.exists()
    response = invitee.post(f'/api/checkers/matches/{match.pk}/accept', {'expected_version': match.version})
    assert response.status_code == 200, response.data
    started = AnalyticsEvent.objects.get(event='game_started')
    assert started.distinct_id == str(dmitry.pk)
    assert started.properties['$session_id'] == invitee_session != inviter_session
    match.refresh_from_db()
    assert (
        invitee.post(f'/api/checkers/matches/{match.pk}/resign', {'expected_version': match.version}).status_code == 200
    )
    assert AnalyticsEvent.objects.get(event='game_completed').distinct_id == str(dmitry.pk)


def test_spectator_cannot_replace_guest_identity_or_opt_out():
    client, anonymous_id, session_id = tracked_client()
    match, _ = create_match(client, 'checkers')
    with request_for(HTTP_X_POSTHOG_DISTINCT_ID=str(uuid4()), HTTP_X_POSTHOG_OPT_OUT='1'):
        match.save()
    participant = GameParticipant.objects.get()
    assert participant.distinct_id == anonymous_id
    assert participant.session_id == session_id and participant.enabled


def test_existing_match_does_not_create_fake_historical_start(settings, bucky):
    client, _, _ = tracked_client(bucky)
    settings.POSTHOG_ENABLED = False
    match, _ = create_match(client, 'checkers')
    settings.POSTHOG_ENABLED = True
    match.save()
    assert not AnalyticsEvent.objects.exists()
    assert not GameParticipant.objects.exists()


def test_in_memory_unsaved_terminal_status_does_not_emit_completion(bucky):
    client, _, _ = tracked_client(bucky)
    match, _ = create_match(client, 'checkers')
    match.status = 'finished'
    match.save(update_fields=['modified_date'])
    assert not AnalyticsEvent.objects.filter(event='game_completed').exists()


def test_signup_links_anonymous_browser_and_sanitizes_attribution(bucky):
    anonymous_id = str(uuid4())
    with request_for(
        HTTP_X_POSTHOG_DISTINCT_ID=anonymous_id,
        HTTP_X_POSTHOG_SESSION_ID=str(uuid4()),
        HTTP_X_POSTHOG_GAME='checkers',
        HTTP_X_POSTHOG_GAME_SOURCE='guest_reward',
        HTTP_X_POSTHOG_GAME_MATCH_ID='12',
        HTTP_X_POSTHOG_REWARD_OFFER_SEEN='1',
        HTTP_X_POSTHOG_REWARD_SIGNUP_CLICKED='1',
    ):
        safely_record(record_signup, bucky)
    signup = AnalyticsEvent.objects.get(event='signup_completed')
    assert signup.distinct_id == str(bucky.pk)
    assert signup.properties['attribution_game'] == 'checkers'
    assert signup.properties['signup_source'] == 'guest_reward'
    assert signup.properties['attribution_match_id'] == 12
    assert signup.properties['reward_signup_clicked']
    assert AnalyticsEvent.objects.get(event='$identify').properties['$anon_distinct_id'] == anonymous_id
    with request_for(HTTP_X_POSTHOG_GAME='password=secret', HTTP_X_POSTHOG_GAME_MATCH_ID='9999999999999999999999'):
        assert request_context()['attribution'] == {}


def test_outbox_retries_use_same_uuid_and_only_acknowledged_events_are_delivered(bucky_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=uuid4())
    event = AnalyticsEvent.objects.get()
    client = Mock()
    client.capture.side_effect = [None, str(event.pk)]
    with patch('thenewboston.product_analytics.tasks.get_client', return_value=client):
        assert deliver_product_analytics() == 0
        event.refresh_from_db()
        assert event.delivered_at is None and event.attempts == 1
        AnalyticsEvent.objects.filter(pk=event.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        assert deliver_product_analytics() == 1
        assert deliver_product_analytics() == 0
    first, second = client.capture.call_args_list
    assert first == second
    assert first.kwargs['uuid'] == str(event.pk)
    assert first.kwargs['timestamp'] == event.occurred_at


def test_verification_is_internal_personless_and_fails_closed():
    client = Mock()
    client.capture.return_value = 'ack'
    with (
        patch('thenewboston.product_analytics.tasks.get_client', return_value=client),
        patch(
            'thenewboston.product_analytics.management.commands.verify_product_analytics.get_client',
            return_value=client,
        ),
    ):
        call_command('verify_product_analytics', deployment_sha='a' * 40)
    event = AnalyticsEvent.objects.get()
    assert event.event == 'analytics_pipeline_verified' and event.delivered_at
    assert event.properties['internal_traffic'] and event.properties['$process_person_profile'] is False
    assert client.capture.call_args.kwargs['options'] == {'process_person_profile': False}
    with patch(
        'thenewboston.product_analytics.management.commands.verify_product_analytics.get_client', return_value=None
    ):
        with pytest.raises(CommandError):
            call_command('verify_product_analytics', deployment_sha='b' * 40)


def test_context_is_reset_after_request_error():
    def fail(request):
        assert current_request.get() is request
        raise RuntimeError('request failed')

    with pytest.raises(RuntimeError):
        AnalyticsContextMiddleware(fail)(SimpleNamespace())
    assert current_request.get() is None


@pytest.mark.parametrize('game', MATCHES)
@pytest.mark.parametrize('authenticated', [False, True])
def test_first_successful_action_engages_once_across_all_games(game, authenticated, bucky):
    from thenewboston.backgammon.rules import legal_turns
    from thenewboston.battleship.tests.test_rules import fleet
    from thenewboston.checkers.rules import legal_moves

    client, anonymous_id, _ = tracked_client(bucky if authenticated else None)
    with (
        patch('thenewboston.backgammon.services.roll_dice', return_value=[6, 1]),
        patch('thenewboston.mancala.services.randbelow', return_value=0),
    ):
        match, _ = create_match(client, game, **({'color': 'black'} if game == 'reversi' else {}))
    assert not AnalyticsEvent.objects.filter(event='game_engaged').exists()
    payloads = {
        'battleship': {'ships': fleet()},
        'connect_five': {'move_type': 'SINGLE', 'x': 0, 'y': 0},
        'dots_and_boxes': {'line': 0},
        'hex': {'cell': 0},
        'mancala': {'pit': 0},
        'reversi': {'row': 2, 'column': 3},
    }
    if game == 'backgammon':
        payload = {'moves': legal_turns(match.board, 'white', match.dice)[0]}
    elif game == 'checkers':
        payload = {'path': legal_moves(match.board, 'white')[0]}
    else:
        payload = payloads[game]
    path = f'/api/{game.replace("_", "-")}/matches/{match.pk}/' + ('place' if game == 'battleship' else 'move')
    response = client.post(path, {'expected_version': match.version, **payload}, format='json')
    assert response.status_code == 200, response.data
    engaged = AnalyticsEvent.objects.get(event='game_engaged')
    assert engaged.distinct_id == (str(bucky.pk) if authenticated else anonymous_id)
    # A stale retry, polling and a duplicate save cannot create a second engaged event.
    client.post(path, {'expected_version': match.version, **payload}, format='json')
    client.get(path.rsplit('/', 1)[0])
    match.refresh_from_db()
    match.save()
    assert AnalyticsEvent.objects.filter(event='game_engaged').count() == 1


@pytest.mark.parametrize('authenticated', [False, True])
def test_read_only_opt_out_suppresses_later_worker_completion(authenticated, bucky):
    from thenewboston.checkers.services import finish_match

    client, _, _ = tracked_client(bucky if authenticated else None)
    match, _ = create_match(client, 'checkers')
    client.credentials(**{**client._credentials, 'HTTP_DNT': '1'})
    assert client.get(f'/api/checkers/matches/{match.pk}').status_code == 200
    assert not GameParticipant.objects.get().enabled
    with transaction.atomic():
        finish_match(match, 'black', 'no_moves')
        match.save()
    assert not AnalyticsEvent.objects.filter(event='game_completed').exists()


def test_guest_identity_is_frozen_after_browser_reset():
    client, anonymous_id, session_id = tracked_client()
    match, _ = create_match(client, 'checkers')
    client.credentials(
        **{**client._credentials, 'HTTP_X_POSTHOG_DISTINCT_ID': str(uuid4()), 'HTTP_X_POSTHOG_SESSION_ID': str(uuid4())}
    )
    assert (
        client.post(f'/api/checkers/matches/{match.pk}/resign', {'expected_version': match.version}).status_code == 200
    )
    completed = AnalyticsEvent.objects.get(event='game_completed')
    assert completed.distinct_id == anonymous_id and completed.properties['$session_id'] == session_id


def test_expired_battleship_placement_does_not_engage():
    from thenewboston.battleship.tests.test_rules import fleet

    client, _, _ = tracked_client()
    match, _ = create_match(client, 'battleship')
    match.placement_deadline = timezone.now() - timedelta(seconds=1)
    match.save()
    response = client.post(
        f'/api/battleship/matches/{match.pk}/place',
        {'expected_version': match.version, 'ships': fleet()},
        format='json',
    )
    assert response.status_code == 200, response.data
    assert AnalyticsEvent.objects.filter(event='game_completed').exists()
    assert not AnalyticsEvent.objects.filter(event='game_engaged').exists()


def test_ai_and_spectator_game_events_do_not_engage(bucky, dmitry):
    from thenewboston.checkers.models import CheckersEvent

    client, _, _ = tracked_client(bucky)
    match, _ = create_match(client, 'checkers')
    CheckersEvent.objects.create(match=match, version=2, event_type='move', payload={'side': 'black'})
    with request_for(dmitry):
        CheckersEvent.objects.create(match=match, version=3, event_type='move', payload={'side': 'white'})
    assert not AnalyticsEvent.objects.filter(event='game_engaged').exists()


def test_connect_five_invitation_preserves_both_participant_identities(bucky_tnb_wallet, dmitry_tnb_wallet):
    from thenewboston.connect_five.models import ConnectFiveMatch

    inviter, _, first_session = tracked_client(bucky_tnb_wallet.owner)
    invitee, _, second_session = tracked_client(dmitry_tnb_wallet.owner)
    response = inviter.post(
        '/api/connect-five/challenges',
        {
            'opponent_id': dmitry_tnb_wallet.owner_id,
            'stake_amount': 0,
            'max_spend_amount': 0,
            'time_limit_seconds': 300,
        },
        format='json',
    )
    assert response.status_code == 201, response.data
    assert not AnalyticsEvent.objects.exists()
    accepted = invitee.post(f'/api/connect-five/challenges/{response.data["id"]}/accept', {}, format='json')
    assert accepted.status_code == 200, accepted.data
    assert set(
        AnalyticsEvent.objects.filter(event='game_started').values_list('properties__$session_id', flat=True)
    ) == {first_session, second_session}
    match = ConnectFiveMatch.objects.get()
    with request_for(bucky_tnb_wallet.owner, HTTP_X_POSTHOG_OPT_OUT='1'):
        match.save(update_fields=['modified_date'])
    assert not GameParticipant.objects.get(user_id=bucky_tnb_wallet.owner_id).enabled
    assert GameParticipant.objects.get(user_id=dmitry_tnb_wallet.owner_id).enabled


def test_signup_endpoint_captures_only_successful_signup_and_links_guest():
    client = APIClient()
    anonymous_id = str(uuid4())
    client.credentials(
        HTTP_X_POSTHOG_DISTINCT_ID=anonymous_id,
        HTTP_X_POSTHOG_GAME='checkers',
        HTTP_X_POSTHOG_GAME_SOURCE='guest_reward',
    )
    with patch('thenewboston.users.serializers.user.INVITE_SYSTEM_ENABLED', False):
        response = client.post(
            '/api/users',
            {'agree_to_terms': True, 'password': 'analytics-test-only-2X!secure', 'username': 'analytics_guest'},
            format='json',
        )
    assert response.status_code == 201, response.data
    signup = AnalyticsEvent.objects.get(event='signup_completed')
    assert signup.properties['signup_source'] == 'guest_reward'
    assert AnalyticsEvent.objects.get(event='$identify').properties['$anon_distinct_id'] == anonymous_id
    assert 'password' not in signup.properties
    assert 'analytics-test-only-2X!secure' not in str(signup.properties)
