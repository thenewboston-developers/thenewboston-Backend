from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.checkers.models import CheckersLedgerEntry, CheckersMatch
from thenewboston.checkers.rules import initial_board, legal_moves, position_key
from thenewboston.checkers.services import queue_computer as enqueue_computer, run_computer
from thenewboston.checkers.tasks import sweep_checkers_matches
from thenewboston.checkers.tests.test_rules import board_with
from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.game_rewards.services import contribute
from thenewboston.notifications.models import Notification

BASE = '/api/checkers/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.checkers.services.queue_computer') as queue:
        yield queue


def create(client, user, opponent=None, **kwargs):
    client.force_authenticate(user)
    payload = {'request_id': str(uuid4()), 'mode': 'human' if opponent else 'computer', **kwargs}
    if opponent:
        payload['opponent_id'] = opponent.id
    return client.post(BASE, payload, format='json')


def action(client, user, match, name, **kwargs):
    client.force_authenticate(user)
    return client.post(f'{BASE}/{match.id}/{name}', {'expected_version': match.version, **kwargs}, format='json')


def accepted_match(client, white, black, **kwargs):
    response = create(client, white, black, **kwargs)
    assert response.status_code == 201, response.data
    match = CheckersMatch.objects.get(pk=response.data['id'])
    response = action(client, black, match, 'accept')
    assert response.status_code == 200, response.data
    match.refresh_from_db()
    return match


def test_free_computer_match_needs_no_wallet(client, bucky):
    response = create(client, bucky)
    assert response.status_code == 201
    assert response.data['status'] == 'active'
    assert response.data['black'] is None
    assert response.data['computer_name'] == 'Computer'
    assert response.data['your_side'] == 'white'
    assert response.data['board'] == initial_board()
    assert len(response.data['legal_moves']) == 7
    assert not CheckersLedgerEntry.objects.exists()


@pytest.mark.parametrize(
    'payload',
    [
        {'mode': 'human'},
        {'stake_amount': 1},
        {'time_limit_seconds': 1},
        {'difficulty': 'impossible'},
        {'stake_amount': -1},
        {'stake_amount': 1000000001},
        {'request_id': 'no'},
    ],
)
def test_invalid_creation_does_not_charge(client, bucky, payload):
    assert create(client, bucky, **payload).status_code == 400
    assert not CheckersMatch.objects.exists()


def test_authentication_self_challenge_and_public_read(client, bucky):
    assert client.get(BASE).status_code == 200
    assert client.post(BASE, {'mode': 'computer'}, format='json').status_code == 401
    assert create(client, bucky, bucky).status_code == 400


def test_insufficient_funds_creation_and_accept_are_atomic(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    assert create(client, bucky, dmitry, stake_amount=1001).status_code == 400
    assert not CheckersMatch.objects.exists()
    response = create(client, bucky, dmitry, stake_amount=100)
    match = CheckersMatch.objects.get(pk=response.data['id'])
    dmitry_tnb_wallet.balance = 0
    dmitry_tnb_wallet.save()
    assert action(client, dmitry, match, 'accept').status_code == 400
    match.refresh_from_db()
    assert match.status == 'pending' and match.prize_pool_total == 100
    assert match.ledger_entries.count() == 1
    assert action(client, bucky, match, 'cancel').status_code == 200
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000


def test_create_retries_are_idempotent_and_mismatched_reuse_conflicts(client, bucky, dmitry, bucky_tnb_wallet):
    request_id = str(uuid4())
    first = create(client, bucky, dmitry, stake_amount=100, request_id=request_id)
    second = create(client, bucky, dmitry, stake_amount=100, request_id=request_id)
    assert first.status_code == second.status_code == 201
    assert first.data['id'] == second.data['id']
    assert create(client, bucky, dmitry, stake_amount=101, request_id=request_id).status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900
    assert CheckersLedgerEntry.objects.count() == 1
    assert Notification.objects.filter(payload__notification_type='CHECKERS_CHALLENGE').count() == 1


@pytest.mark.parametrize('name', ['cancel', 'decline', 'expire'])
def test_pending_challenge_refunds_exactly_once(client, bucky, dmitry, bucky_tnb_wallet, name):
    response = create(client, bucky, dmitry, stake_amount=100)
    match = CheckersMatch.objects.get(pk=response.data['id'])
    if name == 'expire':
        match.expires_at = timezone.now() - timedelta(seconds=1)
        match.save()
        response = action(client, dmitry, match, 'accept')
        assert response.data['status'] == 'expired'
    else:
        response = action(client, bucky if name == 'cancel' else dmitry, match, name)
    assert response.status_code == 200
    sweep_checkers_matches()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert match.ledger_entries.filter(action='refund').count() == 1


def test_pending_invitations_private_and_only_participants_can_mutate(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = CheckersMatch.objects.get(pk=response.data['id'])
    stranger = baker.make('users.User')
    client.force_authenticate(stranger)
    assert client.get(BASE).data['count'] == 0
    assert client.get(f'{BASE}/{match.id}').status_code == 404
    assert action(client, bucky, match, 'accept').status_code == 403
    assert action(client, dmitry, match, 'cancel').status_code == 403
    assert action(client, dmitry, match, 'accept').status_code == 200
    match.refresh_from_db()
    client.force_authenticate(stranger)
    assert client.get(f'{BASE}/{match.id}').data['legal_moves'] == []
    assert action(client, stranger, match, 'resign').status_code == 403
    client.force_authenticate(None)
    assert client.get(f'{BASE}/{match.id}').status_code == 200
    assert client.get(f'{BASE}?mine=true').data['count'] == 0


def test_turns_stale_versions_and_invalid_moves(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    path = legal_moves(match.board, 'white')[0]
    assert action(client, dmitry, match, 'move', path=path).status_code == 403
    assert action(client, bucky, match, 'move', path=[42, 33, 24]).status_code == 400
    response = action(client, bucky, match, 'move', path=path)
    assert response.status_code == 200
    assert response.data['last_move'] == {'side': 'white', 'path': path, 'captured': []}
    assert response.data['active_side'] == 'black'
    assert action(client, bucky, match, 'move', path=path).status_code == 409
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', path=path).status_code == 403


def test_last_capture_pays_stakes_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=123)
    match.board = board_with({42: 1, 35: -1})
    match.save()
    response = action(client, bucky, match, 'move', path=[42, 28])
    assert response.status_code == 200
    assert response.data['status'] == 'finished' and response.data['winner'] == 'white'
    assert response.data['result_reason'] == 'no_moves'
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1123, 877)
    assert sum(match.ledger_entries.values_list('amount', flat=True)) == 0
    sweep_checkers_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1
    assert action(client, bucky, match, 'move', path=[42, 28]).status_code == 409


def test_blocked_opponent_loses_even_with_pieces_remaining(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    match.board = board_with({42: 1, 62: -1})
    match.save()
    response = action(client, bucky, match, 'move', path=[42, 33])
    assert response.data['winner'] == 'white' and response.data['result_reason'] == 'no_moves'


def test_threefold_repetition_refunds_both_stakes_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    match.board = board_with({40: 2, 23: -2})
    match.position_counts = {position_key(match.board, 'white'): 1}
    match.save()
    cycle = [(bucky, [40, 33]), (dmitry, [23, 30]), (bucky, [33, 40]), (dmitry, [30, 23])]
    for user, path in cycle * 2:
        response = action(client, user, match, 'move', path=path)
        assert response.status_code == 200, response.data
        match.refresh_from_db()
    assert response.data['winner'] is None and response.data['result_reason'] == 'repetition'
    sweep_checkers_matches()
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1000, 1000)
    assert match.ledger_entries.filter(action='refund').count() == 2


@pytest.mark.parametrize('piece,finished', [(2, True), (1, False)])
def test_no_progress_draw_after_80_plies_but_man_move_resets_counter(client, bucky, dmitry, piece, finished):
    match = accepted_match(client, bucky, dmitry)
    match.board = board_with({40: piece, 23: -2})
    match.reversible_plies = 79
    match.save()
    response = action(client, bucky, match, 'move', path=[40, 33])
    assert (response.data['status'] == 'finished') is finished
    assert response.data['reversible_plies'] == (80 if finished else 0)
    if finished:
        assert response.data['result_reason'] == 'no_progress'


def test_timeout_from_retrieve_settles_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    match.clock_white_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    client.force_authenticate(bucky)
    response = client.get(f'{BASE}/{match.id}')
    assert response.data['winner'] == 'black'
    assert response.data['result_reason'] == 'timeout'
    sweep_checkers_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1100


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_cpu_moves_once_and_stale_tasks_are_noop(client, bucky, difficulty):
    response = create(client, bucky, difficulty=difficulty)
    match = CheckersMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'move', path=response.data['legal_moves'][0]).status_code == 200
    match.refresh_from_db()
    version = match.version
    run_computer(match.id, version - 1)
    match.refresh_from_db()
    assert match.active_side == 'black'
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.active_side == 'white' and match.version == version + 1
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.version == version + 1


def test_cpu_queue_recovers_after_broker_failure(client, bucky):
    response = create(client, bucky)
    match = CheckersMatch.objects.get(pk=response.data['id'])
    action(client, bucky, match, 'move', path=response.data['legal_moves'][0])
    match.refresh_from_db()
    with patch('thenewboston.checkers.tasks.play_computer_turn.delay', side_effect=[ConnectionError, None]) as delay:
        enqueue_computer(match)
        sweep_checkers_matches()
        assert delay.call_count == 2
        assert all(call.args == (match.id, match.version) for call in delay.call_args_list)


def test_rematch_preserves_terms_and_requires_acceptance(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100, time_limit_seconds=600)
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    first = action(client, dmitry, match, 'rematch')
    second = action(client, bucky, match, 'rematch')
    assert first.status_code == second.status_code == 200
    assert first.data['id'] == second.data['id']
    assert first.data['your_side'] == 'white' and second.data['your_side'] == 'black'
    assert first.data['status'] == 'pending' and first.data['stake_amount'] == 100
    assert first.data['time_limit_seconds'] == 600 and first.data['board'] == initial_board()


def test_computer_win_reward_paid_once(client, bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = create(client, bucky_tnb_wallet.owner)
    match = CheckersMatch.objects.get(pk=response.data['id'])
    match.board = board_with({42: 1, 35: -1})
    match.save()
    response = action(client, bucky_tnb_wallet.owner, match, 'move', path=[42, 28])
    assert response.data['computer_reward'] == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
    sweep_checkers_matches()
    assert action(client, bucky_tnb_wallet.owner, match, 'move', path=[42, 28]).status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010 and GameFund.objects.get().balance == 10
    assert GameRewardDecision.objects.filter(game='checkers', match_id=match.id).count() == 1


@pytest.mark.parametrize('result', ['draw', 'resign', 'computer_timeout'])
def test_computer_nonwins_never_receive_rewards(client, bucky_tnb_wallet, dmitry_tnb_wallet, result):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = create(client, bucky_tnb_wallet.owner)
    match = CheckersMatch.objects.get(pk=response.data['id'])
    if result == 'draw':
        match.board = board_with({40: 2, 23: -2})
        match.reversible_plies = 79
        match.save()
        response = action(client, bucky_tnb_wallet.owner, match, 'move', path=[40, 33])
    elif result == 'resign':
        response = action(client, bucky_tnb_wallet.owner, match, 'resign')
    else:
        match.active_side = 'black'
        match.turn_started_at = timezone.now() - timedelta(seconds=1000)
        match.save()
        response = client.get(f'{BASE}/{match.id}')
    assert response.data['computer_reward']['status'] == 'not_eligible'
    assert response.data['computer_reward']['amount'] == 0
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 and GameFund.objects.get().balance == 20


def test_clock_expiring_during_validation_cannot_accept_a_late_move(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    start = timezone.now()
    match.turn_started_at = start
    match.clock_white_ms = 1000
    match.save()
    original = match.board.copy()
    path = legal_moves(match.board, 'white')[0]
    with patch(
        'thenewboston.checkers.services.timezone.now',
        side_effect=[
            start + timedelta(milliseconds=999),
            start + timedelta(milliseconds=1001),
            *[start + timedelta(milliseconds=1002)] * 20,
        ],
    ):
        response = action(client, bucky, match, 'move', path=path)
    assert response.status_code == 200
    assert response.data['result_reason'] == 'timeout' and response.data['winner'] == 'black'
    assert response.data['board'] == original and response.data['last_move'] is None


def test_capture_resets_no_progress_counter(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    match.board = board_with({42: 2, 35: -1, 1: -1})
    match.reversible_plies = 79
    match.save()
    response = action(client, bucky, match, 'move', path=[42, 28])
    assert response.data['status'] == 'active' and response.data['reversible_plies'] == 0
