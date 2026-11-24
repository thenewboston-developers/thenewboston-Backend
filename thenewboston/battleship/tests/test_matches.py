from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.battleship.models import BattleshipLedgerEntry, BattleshipMatch
from thenewboston.battleship.rules import ship_cells
from thenewboston.battleship.services import queue_computer as enqueue_computer, run_computer
from thenewboston.battleship.tasks import sweep_battleship_matches
from thenewboston.battleship.tests.test_rules import fleet
from thenewboston.notifications.models import Notification

BASE = '/api/battleship/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.battleship.services.queue_computer') as queue:
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


def accepted_match(client, host, guest, **kwargs):
    response = create(client, host, guest, **kwargs)
    assert response.status_code == 201, response.data
    match = BattleshipMatch.objects.get(pk=response.data['id'])
    response = action(client, guest, match, 'accept')
    assert response.status_code == 200, response.data
    match.refresh_from_db()
    return match


def ready_match(client, host, guest, **kwargs):
    match = accepted_match(client, host, guest, **kwargs)
    for user in (host, guest):
        with patch('thenewboston.battleship.services.randbelow', return_value=0):
            response = action(client, user, match, 'place', ships=fleet())
        assert response.status_code == 200, response.data
        match.refresh_from_db()
    assert match.active_side == 'host'
    return match


def test_free_computer_private_fleet_needs_no_wallet(client, bucky):
    response = create(client, bucky)
    assert response.status_code == 201
    assert response.data['phase'] == 'placing'
    assert response.data['guest'] is None
    assert response.data['computer_name'] == 'Computer'
    assert response.data['guest_ready']
    assert not response.data['host_ready']
    assert response.data['board'] == {'ships': [], 'shots': [], 'incoming_shots': [], 'opponent_sunk_ships': []}
    assert BattleshipLedgerEntry.objects.count() == 0
    match = BattleshipMatch.objects.get(pk=response.data['id'])
    assert len(match.fleet_guest) == 5
    assert match.events.get().payload == {}


@pytest.mark.parametrize(
    'payload',
    [
        {'mode': 'computer', 'stake_amount': 1},
        {'mode': 'human'},
        {'difficulty': 'expert'},
        {'time_limit_seconds': 0},
        {'stake_amount': -1},
        {'stake_amount': 1000000001},
        {'request_id': 'no'},
    ],
)
def test_invalid_creation_does_not_charge(client, bucky, payload):
    assert create(client, bucky, **payload).status_code == 400
    assert not BattleshipMatch.objects.exists()


def test_authentication_and_self_challenge(client, bucky):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, {'mode': 'computer'}, format='json').status_code == 401
    assert create(client, bucky, bucky).status_code == 400


def test_insufficient_funds_creation_and_accept_are_atomic(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    assert create(client, bucky, dmitry, stake_amount=1001).status_code == 400
    assert not BattleshipMatch.objects.exists()
    response = create(client, bucky, dmitry, stake_amount=100)
    match = BattleshipMatch.objects.get(pk=response.data['id'])
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
    assert BattleshipLedgerEntry.objects.count() == 1
    assert Notification.objects.filter(payload__notification_type='BATTLESHIP_CHALLENGE').count() == 1


@pytest.mark.parametrize('name', ['cancel', 'decline', 'expire'])
def test_pending_challenge_refunds_exactly_once(client, bucky, dmitry, bucky_tnb_wallet, name):
    response = create(client, bucky, dmitry, stake_amount=100)
    match = BattleshipMatch.objects.get(pk=response.data['id'])
    if name == 'expire':
        match.expires_at = timezone.now() - timedelta(seconds=1)
        match.save()
        response = action(client, dmitry, match, 'accept')
        assert response.data['status'] == 'expired'
    else:
        response = action(client, bucky if name == 'cancel' else dmitry, match, name)
    assert response.status_code == 200
    sweep_battleship_matches()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert match.ledger_entries.filter(action='refund').count() == 1


def test_private_matches_hidden_from_every_nonparticipant(client, bucky, dmitry):
    match = ready_match(client, bucky, dmitry)
    stranger = baker.make('users.User')
    client.force_authenticate(stranger)
    assert client.get(BASE).data['count'] == 0
    assert client.get(f'{BASE}/{match.id}').status_code == 404
    assert action(client, stranger, match, 'fire', row=0, column=0).status_code == 404
    client.force_authenticate(None)
    assert client.get(f'{BASE}/{match.id}').status_code == 401


def test_roles_and_private_placement_in_all_responses(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = BattleshipMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'accept').status_code == 403
    assert action(client, dmitry, match, 'cancel').status_code == 403
    assert action(client, dmitry, match, 'accept').status_code == 200
    match.refresh_from_db()
    host_fleet = fleet()
    guest_fleet = [{**ship, 'column': 4} for ship in fleet()]
    response = action(client, bucky, match, 'place', ships=host_fleet)
    assert response.data['board']['ships'] == host_fleet
    match.refresh_from_db()
    client.force_authenticate(dmitry)
    for snapshot in [client.get(f'{BASE}/{match.id}').data, client.get(BASE).data['results'][0]]:
        assert snapshot['your_side'] == 'guest'
        assert snapshot['board']['ships'] == []
        assert snapshot['board']['opponent_sunk_ships'] == []
        assert 'fleet_host' not in snapshot and 'fleet_guest' not in snapshot
    assert action(client, bucky, match, 'place', ships=guest_fleet).status_code == 409
    response = action(client, dmitry, match, 'place', ships=guest_fleet)
    assert response.status_code == 200
    assert response.data['board']['ships'] == guest_fleet
    assert response.data['board']['opponent_sunk_ships'] == []
    assert all(event.payload in ({}, {'side': 'host'}, {'side': 'guest'}) for event in match.events.all())


@pytest.mark.parametrize(
    'change', ['overlap', 'offboard', 'duplicate', 'incomplete', 'bad_id', 'bad_orientation', 'bad_row']
)
def test_invalid_placement_is_rejected_without_locking_fleet(client, bucky, change):
    response = create(client, bucky)
    match = BattleshipMatch.objects.get(pk=response.data['id'])
    ships = fleet()
    if change == 'overlap':
        ships[1]['row'] = 0
    elif change == 'offboard':
        ships[0]['column'] = 9
    elif change == 'duplicate':
        ships[1]['id'] = ships[0]['id']
    elif change == 'incomplete':
        ships.pop()
    elif change == 'bad_id':
        ships[0]['id'] = []
    elif change == 'bad_orientation':
        ships[0]['orientation'] = {}
    else:
        ships[0]['row'] = []
    assert action(client, bucky, match, 'place', ships=ships).status_code == 400
    match.refresh_from_db()
    assert not match.fleet_host
    assert match.version == 1


def test_alternating_turns_duplicate_and_stale_shots(client, bucky, dmitry):
    match = ready_match(client, bucky, dmitry)
    assert action(client, dmitry, match, 'fire', row=0, column=0).status_code == 403
    assert action(client, bucky, match, 'fire', row=10, column=0).status_code == 400
    response = action(client, bucky, match, 'fire', row=0, column=0)
    assert response.status_code == 200
    assert response.data['last_shot'] == {'side': 'host', 'row': 0, 'column': 0, 'result': 'hit'}
    assert response.data['active_side'] == 'guest'
    assert action(client, bucky, match, 'fire', row=0, column=1).status_code == 409
    match.refresh_from_db()
    assert action(client, dmitry, match, 'fire', row=9, column=9).status_code == 200
    match.refresh_from_db()
    assert action(client, bucky, match, 'fire', row=0, column=0).status_code == 400
    assert len(match.shots_host) == len(match.shots_guest) == 1


def test_full_fleet_sunk_pays_equal_stakes_once_and_only_reveals_sunk_ships(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = ready_match(client, bucky, dmitry, stake_amount=123)
    targets = [cell for ship in fleet() for cell in ship_cells(ship)]
    misses = [(row, column) for row in (1, 3) for column in range(10)]
    for index, (row, column) in enumerate(targets):
        response = action(client, bucky, match, 'fire', row=row, column=column)
        assert response.status_code == 200, response.data
        match.refresh_from_db()
        if index == 3:
            assert response.data['board']['opponent_sunk_ships'] == []
        if index == 4:
            assert response.data['board']['opponent_sunk_ships'] == [fleet()[0]]
        if index < len(targets) - 1:
            row, column = misses[index]
            assert action(client, dmitry, match, 'fire', row=row, column=column).status_code == 200
            match.refresh_from_db()
    assert response.data['status'] == 'finished'
    assert response.data['winner'] == 'host'
    assert response.data['result_reason'] == 'fleet_sunk'
    assert len(response.data['board']['opponent_sunk_ships']) == 5
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1123, 877)
    assert sum(match.ledger_entries.values_list('amount', flat=True)) == 0
    assert action(client, bucky, match, 'fire', row=9, column=9).status_code == 409
    sweep_battleship_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1
    client.force_authenticate(dmitry)
    assert client.get(f'{BASE}/{match.id}').data['board']['opponent_sunk_ships'] == []


@pytest.mark.parametrize('ready_side', [None, 'host', 'guest'])
def test_placement_timeout_pays_ready_player_or_refunds_both(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet, ready_side
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    if ready_side:
        assert (
            action(client, bucky if ready_side == 'host' else dmitry, match, 'place', ships=fleet()).status_code == 200
        )
        match.refresh_from_db()
    match.placement_deadline = timezone.now() - timedelta(seconds=1)
    match.save()
    sweep_battleship_matches()
    sweep_battleship_matches()
    match.refresh_from_db()
    assert match.winner == ready_side
    assert match.status == 'finished'
    assert match.result_reason == ('placement_timeout' if ready_side else 'placement_abandoned')
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    expected = {'host': (1100, 900), 'guest': (900, 1100), None: (1000, 1000)}
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == expected[ready_side]
    assert match.ledger_entries.filter(action='refund').count() == (0 if ready_side else 2)
    assert sum(match.ledger_entries.values_list('amount', flat=True)) == 0


def test_battle_timeout_from_retrieve_settles_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = ready_match(client, bucky, dmitry, stake_amount=100)
    match.clock_host_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    client.force_authenticate(bucky)
    response = client.get(f'{BASE}/{match.id}')
    assert response.data['winner'] == 'guest'
    assert response.data['result_reason'] == 'timeout'
    sweep_battleship_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1100


def test_clock_expiring_during_shot_validation_cannot_accept_a_late_hit(client, bucky, dmitry):
    match = ready_match(client, bucky, dmitry)
    start = timezone.now()
    match.turn_started_at = start
    match.clock_host_ms = 1000
    match.save()
    with patch(
        'thenewboston.battleship.services.timezone.now',
        side_effect=[
            start + timedelta(milliseconds=999),
            start + timedelta(milliseconds=1001),
            *[start + timedelta(milliseconds=1002)] * 20,
        ],
    ):
        response = action(client, bucky, match, 'fire', row=0, column=0)
    assert response.status_code == 200
    assert response.data['result_reason'] == 'timeout'
    assert response.data['winner'] == 'guest'
    assert response.data['board']['shots'] == []


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_cpu_turn_only_gets_public_info_and_duplicate_task_is_noop(client, bucky, difficulty):
    response = create(client, bucky, difficulty=difficulty)
    match = BattleshipMatch.objects.get(pk=response.data['id'])
    with patch('thenewboston.battleship.services.randbelow', return_value=1):
        assert action(client, bucky, match, 'place', ships=fleet()).status_code == 200
    match.refresh_from_db()
    version = match.version
    with patch('thenewboston.battleship.ai.choose_shot', return_value=(9, 9)) as choose:
        run_computer(match.id, version)
        choose.assert_called_once_with([], [], difficulty)
    match.refresh_from_db()
    assert match.active_side == 'host'
    assert match.shots_guest == [{'row': 9, 'column': 9, 'result': 'miss'}]
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.version == version + 1
    assert match.events.filter(event_type='shot').count() == 1


def test_rematch_keeps_stakes_requires_acceptance_and_serializes_for_actor(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100, time_limit_seconds=600)
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    first = action(client, dmitry, match, 'rematch')
    second = action(client, bucky, match, 'rematch')
    assert first.status_code == second.status_code == 200
    assert first.data['id'] == second.data['id']
    assert first.data['your_side'] == 'host'
    assert second.data['your_side'] == 'guest'
    assert first.data['status'] == 'pending'
    assert first.data['stake_amount'] == 100
    assert first.data['time_limit_seconds'] == 600
    assert first.data['board']['ships'] == []
    assert BattleshipMatch.objects.filter(rematch_of=match).count() == 1


def test_computer_rematch_is_free_and_resets_fleet(client, bucky):
    response = create(client, bucky)
    match = BattleshipMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    response = action(client, bucky, match, 'rematch')
    assert response.status_code == 200
    assert response.data['phase'] == 'placing'
    assert response.data['stake_amount'] == 0
    assert response.data['board']['ships'] == []
    assert response.data['guest_ready']


def test_cpu_queue_recovers_after_broker_failure(client, bucky):
    response = create(client, bucky)
    match = BattleshipMatch.objects.get(pk=response.data['id'])
    with patch('thenewboston.battleship.services.randbelow', return_value=1):
        action(client, bucky, match, 'place', ships=fleet())
    match.refresh_from_db()
    with patch('thenewboston.battleship.tasks.play_computer_turn.delay', side_effect=[ConnectionError, None]) as delay:
        enqueue_computer(match)
        sweep_battleship_matches()
        assert delay.call_count == 2
        assert all(call.args == (match.id, match.version) for call in delay.call_args_list)
