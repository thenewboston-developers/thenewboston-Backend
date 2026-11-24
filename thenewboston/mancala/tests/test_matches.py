from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.mancala.models import MancalaLedgerEntry, MancalaMatch
from thenewboston.mancala.rules import initial_board
from thenewboston.mancala.services import queue_computer as enqueue_computer, run_computer
from thenewboston.mancala.tasks import sweep_mancala_matches
from thenewboston.notifications.models import Notification

BASE = '/api/mancala/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.mancala.services.queue_computer') as queue:
        yield queue


def board(host, guest, host_store=0, guest_store=0):
    return [*host, host_store, *guest, guest_store]


def create(client, user, opponent=None, first='host', **kwargs):
    client.force_authenticate(user)
    payload = {'request_id': str(uuid4()), 'mode': 'human' if opponent else 'computer', **kwargs}
    if opponent:
        payload['opponent_id'] = opponent.id
    with patch('thenewboston.mancala.services.randbelow', return_value=0 if first == 'host' else 1):
        return client.post(BASE, payload, format='json')


def action(client, user, match, name, first='host', **kwargs):
    client.force_authenticate(user)
    with patch('thenewboston.mancala.services.randbelow', return_value=0 if first == 'host' else 1):
        return client.post(f'{BASE}/{match.id}/{name}', {'expected_version': match.version, **kwargs}, format='json')


def accepted_match(client, host, guest, first='host', **kwargs):
    response = create(client, host, guest, **kwargs)
    assert response.status_code == 201, response.data
    match = MancalaMatch.objects.get(pk=response.data['id'])
    response = action(client, guest, match, 'accept', first=first)
    assert response.status_code == 200, response.data
    match.refresh_from_db()
    return match


def set_board(match, state, active_side='host'):
    match.board = state
    match.active_side = active_side
    match.save()


def test_free_computer_match_starts_at_once_and_needs_no_wallet(client, bucky, computer_queue):
    response = create(client, bucky, first='guest', difficulty='hard')
    assert response.status_code == 201
    assert response.data['status'] == 'active'
    assert response.data['guest'] is None
    assert response.data['computer_name'] == 'Computer'
    assert response.data['your_side'] == 'host'
    assert response.data['board'] == initial_board()
    assert response.data['active_side'] == 'guest'
    assert response.data['stake_amount'] == response.data['prize_pool_total'] == 0
    assert response.data['recent_moves'] == []
    assert MancalaLedgerEntry.objects.count() == 0
    match = MancalaMatch.objects.get(pk=response.data['id'])
    assert match.events.get().payload == {'first': 'guest'}
    assert computer_queue.call_args.args[0].pk == match.pk


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
    assert not MancalaMatch.objects.exists()


def test_authentication_and_self_challenge(client, bucky):
    assert client.post(BASE, {'mode': 'computer', 'request_id': str(uuid4())}, format='json').status_code == 401
    assert create(client, bucky, bucky).status_code == 400


def test_challenge_locks_the_stake_and_notifies_the_opponent(client, bucky, dmitry, bucky_tnb_wallet):
    response = create(client, bucky, dmitry, stake_amount=100, time_limit_seconds=300)
    assert response.status_code == 201
    assert response.data['status'] == 'pending'
    assert response.data['active_side'] is None
    assert response.data['prize_pool_total'] == 100
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900
    notification = Notification.objects.get()
    assert notification.owner == dmitry
    assert notification.payload == {
        'notification_type': 'MANCALA_CHALLENGE',
        'challenger': {'id': bucky.id, 'username': 'bucky', 'avatar': None},
        'match_id': response.data['id'],
        'stake_amount': 100,
        'time_limit_seconds': 300,
    }


def test_insufficient_funds_creation_and_accept_are_atomic(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    assert create(client, bucky, dmitry, stake_amount=1001).status_code == 400
    assert not MancalaMatch.objects.exists()
    response = create(client, bucky, dmitry, stake_amount=100)
    match = MancalaMatch.objects.get(pk=response.data['id'])
    dmitry_tnb_wallet.balance = 0
    dmitry_tnb_wallet.save()
    assert action(client, dmitry, match, 'accept').status_code == 400
    match.refresh_from_db()
    assert match.status == 'pending' and match.prize_pool_total == 100
    assert match.ledger_entries.count() == 1
    assert action(client, bucky, match, 'cancel').status_code == 200
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000


def test_staked_challenge_needs_a_tnb_wallet(client, bucky, dmitry, tnb_currency):
    assert create(client, bucky, dmitry, stake_amount=1).status_code == 400
    assert create(client, bucky, dmitry).status_code == 201
    assert not MancalaLedgerEntry.objects.exists()


def test_create_retries_are_idempotent_and_mismatched_reuse_conflicts(client, bucky, dmitry, bucky_tnb_wallet):
    request_id = str(uuid4())
    first = create(client, bucky, dmitry, stake_amount=100, request_id=request_id)
    second = create(client, bucky, dmitry, stake_amount=100, request_id=request_id)
    assert first.status_code == second.status_code == 201
    assert first.data['id'] == second.data['id']
    assert create(client, bucky, dmitry, stake_amount=101, request_id=request_id).status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900
    assert MancalaLedgerEntry.objects.count() == 1
    assert Notification.objects.filter(payload__notification_type='MANCALA_CHALLENGE').count() == 1


def test_at_most_ten_unfinished_matches_per_challenger(client, bucky):
    for _ in range(10):
        assert create(client, bucky).status_code == 201
    assert create(client, bucky).status_code == 400
    assert MancalaMatch.objects.count() == 10


@pytest.mark.parametrize('name', ['cancel', 'decline', 'expire'])
def test_pending_challenge_refunds_exactly_once(client, bucky, dmitry, bucky_tnb_wallet, name):
    response = create(client, bucky, dmitry, stake_amount=100)
    match = MancalaMatch.objects.get(pk=response.data['id'])
    if name == 'expire':
        match.expires_at = timezone.now() - timedelta(seconds=1)
        match.save()
        response = action(client, dmitry, match, 'accept')
        assert response.data['status'] == 'expired'
    else:
        response = action(client, bucky if name == 'cancel' else dmitry, match, name)
    assert response.status_code == 200
    sweep_mancala_matches()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert match.ledger_entries.filter(action='refund').count() == 1


def test_only_the_right_player_can_answer_or_cancel_a_challenge(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = MancalaMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'accept').status_code == 403
    assert action(client, bucky, match, 'decline').status_code == 403
    assert action(client, dmitry, match, 'cancel').status_code == 403
    assert action(client, bucky, match, 'move', pit=0).status_code == 409
    assert action(client, dmitry, match, 'accept').status_code == 200


def test_accepting_locks_both_stakes_and_picks_who_moves_first(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, first='guest', stake_amount=100)
    assert (match.status, match.active_side, match.prize_pool_total) == ('active', 'guest', 200)
    assert match.board == initial_board()
    assert match.events.last().payload == {'first': 'guest'}
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (900, 900)


def test_pending_invitations_are_private_but_started_matches_can_be_watched(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = MancalaMatch.objects.get(pk=response.data['id'])
    stranger = baker.make('users.User')
    for viewer in (stranger, None):
        client.force_authenticate(viewer)
        assert client.get(BASE).data['count'] == 0
        assert client.get(f'{BASE}/{match.id}').status_code == 404
    assert action(client, dmitry, match, 'accept').status_code == 200
    match.refresh_from_db()
    for viewer in (stranger, None):
        client.force_authenticate(viewer)
        assert client.get(BASE).data['count'] == 1
        assert client.get(BASE, {'mine': 'exclude', 'status': 'active'}).data['count'] == 1
        assert client.get(BASE, {'mine': 'true'}).data['count'] == 0
        response = client.get(f'{BASE}/{match.id}')
        assert response.status_code == 200
        assert response.data['your_side'] is None
        assert response.data['board'] == initial_board()
    assert action(client, stranger, match, 'move', pit=0).status_code == 403
    client.force_authenticate(None)
    assert client.post(f'{BASE}/{match.id}/move', {'expected_version': match.version, 'pit': 0}).status_code == 401
    client.force_authenticate(bucky)
    assert client.get(BASE, {'mine': 'true'}).data['count'] == 1
    assert client.get(BASE, {'mine': 'exclude'}).data['count'] == 0
    assert client.get(BASE, {'status': 'finished,pending'}).data['count'] == 0
    assert 'recent_moves' not in client.get(BASE).data['results'][0]


def test_turns_alternate_and_stale_or_illegal_moves_are_rejected(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    assert action(client, dmitry, match, 'move', pit=0).status_code == 403
    assert action(client, bucky, match, 'move', pit=6).status_code == 400
    assert action(client, bucky, match, 'move', pit=-1).status_code == 400
    assert action(client, bucky, match, 'move').status_code == 400
    response = action(client, bucky, match, 'move', pit=0)
    assert response.status_code == 200
    assert response.data['board'] == [0, 5, 5, 5, 5, 4, 0, 4, 4, 4, 4, 4, 4, 0]
    assert response.data['active_side'] == 'guest'
    assert response.data['last_move'] == {
        'side': 'host',
        'pit': 0,
        'stones': 4,
        'last': 4,
        'captured': 0,
        'extra_turn': False,
        'swept': None,
    }
    # The same request again is stale and must not move a second pit.
    assert action(client, bucky, match, 'move', pit=1).status_code == 409
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', pit=1).status_code == 403
    response = action(client, dmitry, match, 'move', pit=1)
    assert response.status_code == 200
    assert response.data['board'] == [0, 5, 5, 5, 5, 4, 0, 4, 0, 5, 5, 5, 5, 0]
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', pit=0).status_code == 400
    match.refresh_from_db()
    assert match.version == 4
    assert [event.event_type for event in match.events.all()] == ['created', 'accepted', 'move', 'move']


def test_ending_in_your_store_gives_another_turn_and_keeps_your_clock_running(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    match.turn_started_at = timezone.now() - timedelta(seconds=30)
    match.save()
    response = action(client, bucky, match, 'move', pit=2)
    assert response.status_code == 200
    assert response.data['active_side'] == 'host'
    assert response.data['last_move']['extra_turn']
    assert 568000 <= response.data['clock_host_ms'] <= 570000
    assert response.data['clock_guest_ms'] == 600000
    match.refresh_from_db()
    assert action(client, dmitry, match, 'move', pit=0).status_code == 403
    assert action(client, bucky, match, 'move', pit=5).status_code == 200


def test_recent_moves_replay_what_a_client_missed(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    for user, pit in [(bucky, 2), (bucky, 5), (dmitry, 1)]:
        assert action(client, user, match, 'move', pit=pit).status_code == 200
        match.refresh_from_db()
    client.force_authenticate(None)
    moves = client.get(f'{BASE}/{match.id}').data['recent_moves']
    assert [(move['version'], move['side'], move['pit']) for move in moves] == [
        (3, 'host', 2),
        (4, 'host', 5),
        (5, 'guest', 1),
    ]
    assert moves[0]['board'] == [4, 4, 0, 5, 5, 5, 1, 4, 4, 4, 4, 4, 4, 0]
    assert moves[-1]['board'] == match.board


def test_most_stones_wins_both_stakes_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=123)
    set_board(match, board([0, 0, 0, 0, 0, 1], [1, 2, 3, 0, 0, 0], host_store=26, guest_store=15))
    response = action(client, bucky, match, 'move', pit=5)
    assert response.status_code == 200, response.data
    assert response.data['status'] == 'finished'
    assert response.data['winner'] == 'host'
    assert response.data['result_reason'] == 'stones'
    assert response.data['active_side'] is None
    assert response.data['board'] == board([0] * 6, [0] * 6, host_store=27, guest_store=21)
    assert response.data['last_move']['swept'] == {'host': 0, 'guest': 6}
    assert response.data['computer_reward'] is None
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1123, 877)
    assert sum(match.ledger_entries.values_list('amount', flat=True)) == 0
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', pit=0).status_code == 409
    assert action(client, dmitry, match, 'resign').status_code == 409
    sweep_mancala_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1


def test_the_player_who_empties_their_row_can_still_lose(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=50)
    set_board(match, board([0, 0, 0, 0, 0, 1], [1, 2, 3, 0, 0, 0], host_store=20, guest_store=21))
    response = action(client, bucky, match, 'move', pit=5)
    assert response.data['winner'] == 'guest'
    assert response.data['result_reason'] == 'stones'
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1050


def test_a_draw_refunds_both_stakes(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    set_board(match, board([0, 0, 0, 0, 0, 1], [1, 2, 0, 0, 0, 0], host_store=23, guest_store=21))
    response = action(client, bucky, match, 'move', pit=5)
    assert response.status_code == 200, response.data
    assert response.data['status'] == 'finished'
    assert response.data['winner'] is None
    assert response.data['result_reason'] == 'draw'
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1000, 1000)
    assert match.ledger_entries.filter(action='refund').count() == 2
    assert not match.ledger_entries.filter(action='payout').exists()
    assert sum(match.ledger_entries.values_list('amount', flat=True)) == 0


def test_resigning_pays_the_opponent(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, first='guest', stake_amount=100)
    response = action(client, bucky, match, 'resign')
    assert response.status_code == 200
    assert (response.data['winner'], response.data['result_reason']) == ('guest', 'resignation')
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1100
    assert match.events.last().payload == {'side': 'host'}


@pytest.mark.parametrize('viewer', ['player', 'spectator', 'sweep'])
def test_running_out_of_time_loses_and_settles_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet, viewer):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    match.clock_host_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    if viewer == 'sweep':
        sweep_mancala_matches()
        client.force_authenticate(bucky)
    else:
        client.force_authenticate(bucky if viewer == 'player' else None)
    response = client.get(f'{BASE}/{match.id}')
    assert response.status_code == 200
    assert response.data['status'] == 'finished'
    assert response.data['winner'] == 'guest'
    assert response.data['result_reason'] == 'timeout'
    assert response.data['clock_host_ms'] == 0
    sweep_mancala_matches()
    assert client.get(f'{BASE}/{match.id}').data['version'] == response.data['version']
    assert match.ledger_entries.filter(action='payout').count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1100


def test_list_filters_on_a_detail_read_cannot_break_settling_an_expired_clock(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    match.clock_host_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    client.force_authenticate(dmitry)
    response = client.get(f'{BASE}/{match.id}', {'status': 'active', 'mine': 'true'})
    assert response.status_code == 200
    assert (response.data['status'], response.data['result_reason']) == ('finished', 'timeout')
    assert client.get(f'{BASE}/{match.id}', {'status': 'active'}).status_code == 404


def test_reading_a_healthy_match_changes_nothing(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    client.force_authenticate(dmitry)
    with patch('thenewboston.mancala.views.advance_deadlines') as advance:
        response = client.get(f'{BASE}/{match.id}')
    advance.assert_not_called()
    assert response.data['version'] == match.version
    assert response.data['your_side'] == 'guest'


def test_clock_expiring_while_the_move_is_validated_cannot_accept_a_late_move(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    start = timezone.now()
    match.turn_started_at = start
    match.clock_host_ms = 1000
    match.save()
    with patch(
        'thenewboston.mancala.services.timezone.now',
        side_effect=[
            start + timedelta(milliseconds=999),
            start + timedelta(milliseconds=1001),
            *[start + timedelta(milliseconds=1002)] * 20,
        ],
    ):
        response = action(client, bucky, match, 'move', pit=0)
    assert response.status_code == 200
    assert response.data['result_reason'] == 'timeout'
    assert response.data['winner'] == 'guest'
    assert response.data['board'] == initial_board()
    assert response.data['last_move'] is None


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_computer_turn_plays_one_pit_and_a_duplicate_task_is_a_noop(client, bucky, difficulty, computer_queue):
    response = create(client, bucky, first='guest', difficulty=difficulty)
    match = MancalaMatch.objects.get(pk=response.data['id'])
    version = match.version
    with patch('thenewboston.mancala.ai.choose_pit', return_value=0) as choose:
        run_computer(match.id, version)
        choose.assert_called_once_with(initial_board(), 'guest', difficulty)
    match.refresh_from_db()
    assert match.active_side == 'host'
    assert match.board == [4, 4, 4, 4, 4, 4, 0, 0, 5, 5, 5, 5, 4, 0]
    assert match.last_move['side'] == 'guest'
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.version == version + 1
    assert match.events.filter(event_type='move').count() == 1


def test_computer_queues_itself_again_after_earning_another_turn(client, bucky, computer_queue):
    response = create(client, bucky, first='guest')
    match = MancalaMatch.objects.get(pk=response.data['id'])
    computer_queue.reset_mock()
    with patch('thenewboston.mancala.ai.choose_pit', return_value=2):
        run_computer(match.id, match.version)
    match.refresh_from_db()
    assert match.active_side == 'guest'
    assert match.last_move['extra_turn']
    queued = computer_queue.call_args.args[0]
    assert (queued.pk, queued.version) == (match.pk, match.version)


def test_computer_does_not_move_out_of_turn_or_after_its_clock_ran_out(client, bucky):
    response = create(client, bucky, first='host')
    match = MancalaMatch.objects.get(pk=response.data['id'])
    run_computer(match.id, match.version)
    match.refresh_from_db()
    assert match.version == 1 and match.board == initial_board()
    assert action(client, bucky, match, 'move', pit=0).status_code == 200
    match.refresh_from_db()
    match.clock_guest_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    run_computer(match.id, match.version)
    match.refresh_from_db()
    assert (match.status, match.winner, match.result_reason) == ('finished', 'host', 'timeout')
    assert match.computer_reward == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}


def test_computer_turn_is_queued_after_the_players_move(client, bucky, computer_queue):
    response = create(client, bucky, first='host')
    match = MancalaMatch.objects.get(pk=response.data['id'])
    computer_queue.reset_mock()
    assert action(client, bucky, match, 'move', pit=0).status_code == 200
    queued = computer_queue.call_args.args[0]
    assert (queued.active_side, queued.version) == ('guest', 2)


def test_computer_queue_recovers_after_broker_failure(client, bucky):
    response = create(client, bucky, first='guest')
    match = MancalaMatch.objects.get(pk=response.data['id'])
    with patch('thenewboston.mancala.tasks.play_computer_turn.delay', side_effect=[ConnectionError, None]) as delay:
        enqueue_computer(match)
        sweep_mancala_matches()
        assert delay.call_count == 2
        assert all(call.args == (match.id, match.version) for call in delay.call_args_list)


def test_rematch_keeps_the_terms_requires_acceptance_and_is_shared(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100, time_limit_seconds=900)
    assert action(client, dmitry, match, 'rematch').status_code == 409
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    first = action(client, dmitry, match, 'rematch')
    second = action(client, bucky, match, 'rematch')
    assert first.status_code == second.status_code == 200
    assert first.data['id'] == second.data['id'] != match.id
    assert first.data['your_side'] == 'host'
    assert second.data['your_side'] == 'guest'
    assert first.data['status'] == 'pending'
    assert first.data['stake_amount'] == 100
    assert first.data['time_limit_seconds'] == 900
    assert first.data['rematch_of'] == match.id
    assert MancalaMatch.objects.filter(rematch_of=match).count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    # 1000 - 100 stake + 200 prize - 100 stake for the rematch
    assert dmitry_tnb_wallet.balance == 1000


def test_computer_rematch_is_free_and_starts_a_fresh_board(client, bucky):
    response = create(client, bucky, difficulty='easy', time_limit_seconds=300)
    match = MancalaMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'move', pit=0).status_code == 200
    match.refresh_from_db()
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    response = action(client, bucky, match, 'rematch')
    assert response.status_code == 200
    assert response.data['id'] != match.id
    assert response.data['status'] == 'active'
    assert response.data['board'] == initial_board()
    assert (response.data['difficulty'], response.data['time_limit_seconds']) == ('easy', 300)
    assert response.data['stake_amount'] == 0
