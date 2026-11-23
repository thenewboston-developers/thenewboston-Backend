from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import transaction
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.backgammon.models import BackgammonEvent, BackgammonLedgerEntry, BackgammonMatch
from thenewboston.backgammon.rules import initial_board, legal_turns
from thenewboston.backgammon.services import can_double, run_computer
from thenewboston.backgammon.tasks import sweep_backgammon_matches

BASE = '/api/backgammon/matches'


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.backgammon.services.queue_computer') as queue:
        yield queue


def create(client, user, opponent=None, **kwargs):
    client.force_authenticate(user)
    payload = {'request_id': str(uuid4()), 'mode': 'human' if opponent else 'computer', **kwargs}
    if opponent:
        payload['opponent_id'] = opponent.id
    return client.post(BASE, payload)


def action(client, user, match, name, **kwargs):
    client.force_authenticate(user)
    return client.post(f'{BASE}/{match.id}/{name}', {'expected_version': match.version, **kwargs})


def accepted_match(client, bucky, dmitry, **kwargs):
    response = create(client, bucky, dmitry, **kwargs)
    assert response.status_code == 201, response.data
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    response = action(client, dmitry, match, 'accept')
    assert response.status_code == 200, response.data
    match.refresh_from_db()
    return match


def winning_board(*, multiplier=1):
    board = initial_board()
    board['points'] = [0] * 24
    board['points'][0] = 1
    board['off']['white'] = 14
    board['off']['black'] = 1 if multiplier == 1 else 0
    board['points'][2 if multiplier == 3 else 6] = -(15 - board['off']['black'])
    return board


@pytest.mark.django_db
def test_free_computer_needs_no_currency_or_wallet(client, bucky):
    with patch('thenewboston.backgammon.services.roll_dice', return_value=[6, 1]):
        response = create(client, bucky)
    assert response.status_code == 201
    assert response.data['mode'] == 'computer'
    assert response.data['black'] is None
    assert response.data['computer_name'] == 'Computer'
    assert response.data['phase'] == 'moving'
    assert response.data['dice'] == [6, 1]
    assert response.data['active_side'] == 'white'
    assert response.data['legal_turns']
    assert response.data['scores'] == {'white': 0, 'black': 0}
    assert response.data['server_time']
    assert BackgammonLedgerEntry.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    'payload',
    [
        {'mode': 'computer', 'stake_amount': 1},
        {'mode': 'human'},
        {'mode': 'computer', 'target_score': 2},
        {'mode': 'computer', 'difficulty': 'expert'},
        {'mode': 'computer', 'time_limit_seconds': 0},
        {'mode': 'computer', 'stake_amount': -1},
        {'mode': 'computer', 'stake_amount': 1000000001},
    ],
)
def test_invalid_creation_is_rejected(client, bucky, payload):
    client.force_authenticate(bucky)
    assert client.post(BASE, payload).status_code == 400
    assert BackgammonMatch.objects.count() == 0


@pytest.mark.django_db
def test_create_requires_authentication_and_self_challenge_rejected(client, bucky):
    assert client.post(BASE, {'mode': 'computer'}).status_code == 401
    assert create(client, bucky, bucky).status_code == 400


@pytest.mark.django_db
def test_paid_challenge_escrows_both_and_resignation_pays_once(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (900, 900)
    assert match.prize_pool_total == 200
    response = action(client, dmitry, match, 'resign')
    assert response.status_code == 200
    assert response.data['winner'] == 'white'
    assert response.data['status'] == 'finished'
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1100, 900)
    assert action(client, dmitry, match, 'resign').status_code == 409
    match.refresh_from_db()
    assert action(client, dmitry, match, 'resign').status_code == 409
    assert list(match.ledger_entries.order_by('id').values_list('amount', flat=True)) == [-100, -100, 200]


@pytest.mark.django_db
@pytest.mark.parametrize('name', ['cancel', 'decline'])
def test_challenge_refund(client, bucky, dmitry, bucky_tnb_wallet, name):
    response = create(client, bucky, dmitry, stake_amount=100)
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    actor = bucky if name == 'cancel' else dmitry
    assert action(client, actor, match, name).status_code == 200
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert match.ledger_entries.filter(action='refund').count() == 1
    assert action(client, actor, match, name).status_code == 409


@pytest.mark.django_db
def test_insufficient_balance_creation_and_accept_are_atomic(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    assert create(client, bucky, dmitry, stake_amount=1001).status_code == 400
    assert BackgammonMatch.objects.count() == 0
    response = create(client, bucky, dmitry, stake_amount=1000)
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    dmitry_tnb_wallet.balance = 10
    dmitry_tnb_wallet.save()
    assert action(client, dmitry, match, 'accept').status_code == 400
    match.refresh_from_db()
    assert match.status == 'pending'
    assert match.prize_pool_total == 1000
    assert match.ledger_entries.count() == 1
    assert action(client, bucky, match, 'cancel').status_code == 200
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000


@pytest.mark.django_db
def test_expired_accept_commits_refund(client, bucky, dmitry, bucky_tnb_wallet):
    response = create(client, bucky, dmitry, stake_amount=100)
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    match.expires_at = timezone.now() - timedelta(seconds=1)
    match.save()
    response = action(client, dmitry, match, 'accept')
    assert response.status_code == 200
    assert response.data['status'] == 'expired'
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    sweep_backgammon_matches()
    assert match.ledger_entries.filter(action='refund').count() == 1


@pytest.mark.django_db
def test_pending_visibility_roles_and_authenticated_mutations(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'accept').status_code == 403
    assert action(client, dmitry, match, 'cancel').status_code == 403
    stranger = baker.make('users.User')
    assert action(client, stranger, match, 'accept').status_code == 404
    assert client.get(f'{BASE}/{match.id}').status_code == 404
    client.force_authenticate(None)
    assert client.get(BASE).data['count'] == 0
    assert client.post(f'{BASE}/{match.id}/accept', {'expected_version': match.version}).status_code == 401


@pytest.mark.django_db
def test_public_spectator_has_no_moves_or_mutation_permissions(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    client.force_authenticate(None)
    response = client.get(f'{BASE}/{match.id}')
    assert response.status_code == 200
    assert response.data['legal_turns'] == []
    assert response.data['can_double'] is False
    assert response.data['board'] == match.board
    assert client.get(f'{BASE}?mine=true').data['count'] == 0
    stranger = baker.make('users.User')
    assert action(client, stranger, match, 'resign').status_code == 403


@pytest.mark.django_db
def test_complete_turn_validation_and_stale_replay(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    active = bucky if match.active_side == 'white' else dmitry
    inactive = dmitry if active == bucky else bucky
    moves = legal_turns(match.board, match.active_side, match.dice)[0]
    board_before = match.board
    assert action(client, inactive, match, 'move', moves=moves).status_code == 403
    assert action(client, active, match, 'move', moves=[]).status_code == 400
    match.refresh_from_db()
    assert match.board == board_before
    response = action(client, active, match, 'move', moves=moves)
    assert response.status_code == 200
    assert response.data['phase'] == 'awaiting_roll'
    assert response.data['active_side'] != match.active_side
    assert action(client, active, match, 'move', moves=moves).status_code == 409
    match.refresh_from_db()
    response = action(client, inactive, match, 'roll')
    assert response.status_code == 200
    match.refresh_from_db()
    assert action(client, inactive, match, 'roll').status_code == 409
    assert len(match.dice) == 2 and all(1 <= die <= 6 for die in match.dice)


@pytest.mark.django_db
def test_every_detail_mutation_requires_version(client, bucky):
    response = create(client, bucky)
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    assert client.post(f'{BASE}/{match.id}/resign', {}).status_code == 400
    assert client.post(f'{BASE}/{match.id}/resign', {'expected_version': match.version + 1}).status_code == 409


@pytest.mark.django_db
def test_creation_retry_returns_same_match_and_debits_once(client, bucky, dmitry, bucky_tnb_wallet):
    request_id = str(uuid4())
    first = create(client, bucky, dmitry, stake_amount=100, request_id=request_id)
    retry = create(client, bucky, dmitry, stake_amount=100, request_id=request_id)
    assert first.status_code == retry.status_code == 201
    assert first.data['id'] == retry.data['id']
    assert BackgammonMatch.objects.count() == 1
    assert BackgammonLedgerEntry.objects.count() == 1
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900
    assert create(client, bucky, dmitry, stake_amount=200, request_id=request_id).status_code == 409
    assert BackgammonLedgerEntry.objects.count() == 1


@pytest.mark.django_db
def test_cube_accept_ownership_and_fixed_tnb(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100, target_score=5)
    match.active_side = 'white'
    match.phase = 'awaiting_roll'
    match.dice = []
    match.save()
    response = action(client, bucky, match, 'double')
    assert response.status_code == 200
    assert response.data['clock_side'] == 'black'
    match.refresh_from_db()
    assert action(client, bucky, match, 'respond-double', accept=True).status_code == 403
    response = action(client, dmitry, match, 'respond-double', accept=True)
    assert response.status_code == 200
    assert response.data['cube_value'] == 2
    assert response.data['cube_owner'] == 'black'
    assert response.data['prize_pool_total'] == 200
    match.refresh_from_db()
    assert action(client, bucky, match, 'double').status_code == 409
    assert match.ledger_entries.count() == 2


@pytest.mark.django_db
def test_dropped_double_scores_previous_cube_and_crawford(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry, target_score=3)
    match.active_side = 'white'
    match.phase = 'awaiting_roll'
    match.dice = []
    match.score_white = 1
    match.save()
    assert action(client, bucky, match, 'double').status_code == 200
    match.refresh_from_db()
    response = action(client, dmitry, match, 'respond-double', accept=False)
    assert response.status_code == 200
    assert response.data['scores'] == {'white': 2, 'black': 0}
    assert response.data['status'] == 'between_games'
    assert response.data['result_points'] == 1
    assert response.data['next_game_at']
    match.refresh_from_db()
    response = action(client, dmitry, match, 'next-game')
    assert response.status_code == 200
    assert response.data['is_crawford'] is True
    match.refresh_from_db()
    match.active_side = 'white'
    match.phase = 'awaiting_roll'
    match.dice = []
    match.save()
    assert action(client, bucky, match, 'double').status_code == 409
    match.status = 'between_games'
    match.phase = 'game_over'
    match.score_black = 1
    match.save()
    response = action(client, bucky, match, 'next-game')
    assert response.data['is_crawford'] is False
    assert response.data['crawford_used'] is True


@pytest.mark.django_db
@pytest.mark.parametrize('multiplier', [1, 2, 3])
def test_bearing_off_scores_game_and_pays_only_match_prize(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet, multiplier
):
    match = accepted_match(client, bucky, dmitry, target_score=1, stake_amount=50)
    match.board = winning_board(multiplier=multiplier)
    match.active_side = 'white'
    match.dice = [1, 2]
    match.phase = 'moving'
    match.save()
    moves = legal_turns(match.board, 'white', match.dice)[0]
    response = action(client, bucky, match, 'move', moves=moves)
    assert response.status_code == 200
    assert response.data['result_points'] == multiplier
    assert response.data['scores']['white'] == multiplier
    assert response.data['winner'] == 'white'
    assert response.data['result_reason'] == ['single', 'gammon', 'backgammon'][multiplier - 1]
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1050, 950)


@pytest.mark.django_db
def test_timeout_from_action_commits_payout_and_sweep_does_not_repeat(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    match.active_side = 'black'
    match.phase = 'awaiting_roll'
    match.dice = []
    match.clock_black_ms = 1000
    match.turn_started_at = timezone.now() - timedelta(seconds=2)
    match.save()
    response = action(client, dmitry, match, 'roll')
    assert response.status_code == 200
    assert response.data['status'] == 'finished'
    assert response.data['result_reason'] == 'timeout'
    assert response.data['winner'] == 'white'
    sweep_backgammon_matches()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1100
    assert match.ledger_entries.filter(action='payout').count() == 1


@pytest.mark.django_db
def test_sweep_expires_challenge_and_restarts_between_games(client, bucky, dmitry, bucky_tnb_wallet):
    response = create(client, bucky, dmitry, stake_amount=100)
    pending = BackgammonMatch.objects.get(pk=response.data['id'])
    pending.expires_at = timezone.now() - timedelta(seconds=1)
    pending.save()
    match = accepted_match(client, bucky, dmitry)
    match.status = 'between_games'
    match.phase = 'game_over'
    match.turn_started_at = None
    match.clock_white_ms = 12345
    match.next_game_at = timezone.now() - timedelta(seconds=1)
    match.save()
    sweep_backgammon_matches()
    pending.refresh_from_db()
    match.refresh_from_db()
    assert pending.status == 'expired'
    assert match.status == 'active'
    assert match.game_number == 2
    assert match.clock_white_ms == 12345
    assert match.next_game_at is None
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000


@pytest.mark.django_db
def test_computer_turn_is_legal_and_duplicate_task_is_noop(client, bucky):
    with patch('thenewboston.backgammon.services.roll_dice', return_value=[1, 6]):
        response = create(client, bucky)
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    version = match.version
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.active_side == 'white'
    assert match.phase == 'awaiting_roll'
    assert match.version == version + 1
    assert match.board != initial_board()
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.version == version + 1
    assert BackgammonEvent.objects.filter(match=match, event_type='move').count() == 1


@pytest.mark.django_db
def test_cpu_responds_to_cube_without_spending(client, bucky):
    response = create(client, bucky)
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    match.active_side = 'white'
    match.phase = 'awaiting_roll'
    match.dice = []
    match.save()
    assert action(client, bucky, match, 'double').status_code == 200
    match.refresh_from_db()
    run_computer(match.id, match.version)
    match.refresh_from_db()
    assert match.phase == 'awaiting_roll'
    assert match.cube_owner == 'black'
    assert match.cube_value == 2
    assert match.active_side == 'white'
    assert match.ledger_entries.count() == 0


@pytest.mark.django_db
def test_rematch_same_terms_needs_acceptance_and_cannot_duplicate(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, target_score=5, stake_amount=100)
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    response = action(client, dmitry, match, 'rematch')
    assert response.status_code == 200
    new_id = response.data['id']
    assert response.data['white']['id'] == dmitry.id
    assert response.data['black']['id'] == bucky.id
    assert response.data['status'] == 'pending'
    assert response.data['target_score'] == 5
    assert response.data['stake_amount'] == 100
    assert action(client, bucky, match, 'rematch').data['id'] == new_id
    assert BackgammonMatch.objects.filter(rematch_of=match).count() == 1
    assert BackgammonLedgerEntry.objects.filter(match_id=new_id).count() == 1


@pytest.mark.django_db
def test_one_point_match_has_no_cube(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry, target_score=1)
    assert match.is_crawford
    match.phase = 'awaiting_roll'
    assert not can_double(match)


@pytest.mark.django_db
def test_turn_roll_audit_and_financial_conservation(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=123)
    assert action(client, bucky, match, 'resign').status_code == 200
    assert list(match.events.values_list('version', flat=True)) == [1, 2, 3]
    assert sum(match.ledger_entries.values_list('amount', flat=True)) == 0
    with transaction.atomic():
        match.refresh_from_db()
        assert match.settled
