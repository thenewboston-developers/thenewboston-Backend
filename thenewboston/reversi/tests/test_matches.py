from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.game_rewards.services import contribute
from thenewboston.notifications.models import Notification
from thenewboston.reversi.models import ReversiLedgerEntry, ReversiMatch
from thenewboston.reversi.rules import initial_board, legal_moves
from thenewboston.reversi.services import queue_computer as enqueue_computer, run_computer
from thenewboston.reversi.tasks import sweep_reversi_matches
from thenewboston.reversi.tests.test_rules import PASS_BOARD, full_board

BASE = '/api/reversi/matches'
# White to move. Either white move leaves black without a reply.
WHITE_PASS_BOARD = [row.replace('b', 'x').replace('w', 'b').replace('x', 'w') for row in PASS_BOARD]
pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.reversi.services.queue_computer') as queue:
        yield queue


def create(client, user, opponent=None, **kwargs):
    client.force_authenticate(user)
    payload = {'request_id': str(uuid4()), 'mode': 'human' if opponent else 'computer', 'color': 'black', **kwargs}
    if opponent:
        payload['opponent_id'] = opponent.id
    return client.post(BASE, payload, format='json')


def action(client, user, match, name, **kwargs):
    client.force_authenticate(user)
    return client.post(f'{BASE}/{match.id}/{name}', {'expected_version': match.version, **kwargs}, format='json')


def move(client, user, match, row, column):
    response = action(client, user, match, 'move', row=row, column=column)
    match.refresh_from_db()
    return response


def accepted_match(client, host, guest, **kwargs):
    response = create(client, host, guest, **kwargs)
    assert response.status_code == 201, response.data
    match = ReversiMatch.objects.get(pk=response.data['id'])
    response = action(client, guest, match, 'accept')
    assert response.status_code == 200, response.data
    match.refresh_from_db()
    return match


def computer_match(client, user, **kwargs):
    response = create(client, user, **kwargs)
    assert response.status_code == 201, response.data
    return ReversiMatch.objects.get(pk=response.data['id'])


def set_board(match, board, active_side='black'):
    match.board = board
    match.active_side = active_side
    match.save()


def test_free_computer_match_starts_at_once_and_needs_no_wallet(client, bucky):
    response = create(client, bucky, difficulty='hard', time_limit_seconds=300)
    assert response.status_code == 201
    data = response.data
    assert data['status'] == 'active'
    assert data['black']['username'] == 'bucky'
    assert data['white'] is None
    assert data['computer_name'] == 'Computer'
    assert (data['host_side'], data['active_side'], data['difficulty']) == ('black', 'black', 'hard')
    assert data['board'] == initial_board()
    assert data['scores'] == {'black': 2, 'white': 2}
    assert data['legal_moves'] == [[2, 3], [3, 2], [4, 5], [5, 4]]
    assert (data['clock_black_ms'], data['clock_white_ms']) == (300000, 300000)
    assert data['computer_reward'] is None
    assert ReversiLedgerEntry.objects.count() == 0
    match = ReversiMatch.objects.get(pk=data['id'])
    assert match.events.get().payload == {'host_side': 'black'}


def test_computer_moves_first_when_the_player_takes_white(client, bucky, computer_queue):
    response = create(client, bucky, color='white')
    assert response.data['white']['username'] == 'bucky'
    assert response.data['black'] is None
    assert response.data['active_side'] == 'black'
    match = ReversiMatch.objects.get(pk=response.data['id'])
    computer_queue.assert_called_once_with(match)
    assert action(client, bucky, match, 'move', row=2, column=3).status_code == 403
    run_computer(match.pk, match.version)
    match.refresh_from_db()
    assert match.active_side == 'white'
    assert match.move_count == 1
    assert match.last_move['side'] == 'black'
    assert (match.last_move['row'], match.last_move['column']) in legal_moves(initial_board(), 'black')
    assert match.clock_black_ms <= 900000


@pytest.mark.parametrize('roll,side', [(0, 'black'), (1, 'white')])
def test_random_color_is_decided_by_the_server(client, bucky, dmitry, roll, side):
    with patch('thenewboston.reversi.services.randbelow', return_value=roll):
        response = create(client, bucky, dmitry, color='random')
    assert response.data['host_side'] == side
    assert response.data[side]['username'] == 'bucky'


@pytest.mark.parametrize(
    'payload',
    [
        {'mode': 'computer', 'stake_amount': 1},
        {'mode': 'human'},
        {'difficulty': 'expert'},
        {'color': 'green'},
        {'time_limit_seconds': 0},
        {'stake_amount': -1},
        {'stake_amount': 1000000001},
        {'request_id': 'no'},
    ],
)
def test_invalid_creation_does_not_create_or_charge(client, bucky, bucky_tnb_wallet, payload):
    assert create(client, bucky, **payload).status_code == 400
    assert not ReversiMatch.objects.exists()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000


def test_authentication_and_self_challenge(client, bucky):
    assert client.post(BASE, {'mode': 'computer', 'request_id': str(uuid4())}, format='json').status_code == 401
    assert create(client, bucky, bucky).status_code == 400
    match = computer_match(client, bucky)
    client.force_authenticate(None)
    assert client.post(f'{BASE}/{match.id}/resign', {'expected_version': 1}, format='json').status_code == 401


def test_challenge_locks_the_stake_and_notifies_the_opponent(client, bucky, dmitry, bucky_tnb_wallet):
    response = create(client, bucky, dmitry, stake_amount=100, time_limit_seconds=600)
    assert response.status_code == 201
    assert (response.data['status'], response.data['prize_pool_total']) == ('pending', 100)
    assert response.data['active_side'] is None and response.data['legal_moves'] == []
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900
    notification = Notification.objects.get(owner=dmitry)
    assert notification.payload == {
        'notification_type': 'REVERSI_CHALLENGE',
        'challenger': {'id': bucky.id, 'username': 'bucky', 'avatar': None},
        'match_id': response.data['id'],
        'stake_amount': 100,
        'time_limit_seconds': 600,
    }


def test_insufficient_funds_creation_and_accept_are_atomic(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    assert create(client, bucky, dmitry, stake_amount=1001).status_code == 400
    assert not ReversiMatch.objects.exists()
    response = create(client, bucky, dmitry, stake_amount=100)
    match = ReversiMatch.objects.get(pk=response.data['id'])
    dmitry_tnb_wallet.balance = 99
    dmitry_tnb_wallet.save()
    assert action(client, dmitry, match, 'accept').status_code == 400
    match.refresh_from_db()
    assert match.status == 'pending' and match.prize_pool_total == 100
    assert match.ledger_entries.count() == 1
    assert action(client, bucky, match, 'cancel').status_code == 200
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000


def test_staked_challenge_requires_a_wallet(client, bucky, dmitry, tnb_currency):
    assert create(client, bucky, dmitry, stake_amount=5).status_code == 400
    assert not ReversiMatch.objects.exists()
    assert create(client, bucky, dmitry).status_code == 201


def test_create_retries_are_idempotent_and_mismatched_reuse_conflicts(client, bucky, dmitry, bucky_tnb_wallet):
    request_id = str(uuid4())
    first = create(client, bucky, dmitry, stake_amount=100, request_id=request_id)
    second = create(client, bucky, dmitry, stake_amount=100, request_id=request_id)
    random_color = create(client, bucky, dmitry, stake_amount=100, request_id=request_id, color='random')
    assert first.status_code == second.status_code == random_color.status_code == 201
    assert first.data['id'] == second.data['id'] == random_color.data['id']
    assert create(client, bucky, dmitry, stake_amount=101, request_id=request_id).status_code == 409
    assert create(client, bucky, dmitry, stake_amount=100, request_id=request_id, color='white').status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900
    assert ReversiLedgerEntry.objects.count() == 1
    assert Notification.objects.filter(payload__notification_type='REVERSI_CHALLENGE').count() == 1


def test_open_match_limit(client, bucky):
    for _ in range(10):
        assert create(client, bucky).status_code == 201
    assert create(client, bucky).status_code == 400
    match = ReversiMatch.objects.first()
    assert action(client, bucky, match, 'resign').status_code == 200
    assert create(client, bucky).status_code == 201


@pytest.mark.parametrize('name', ['cancel', 'decline', 'expire'])
def test_pending_challenge_refunds_exactly_once(client, bucky, dmitry, bucky_tnb_wallet, name):
    response = create(client, bucky, dmitry, stake_amount=100)
    match = ReversiMatch.objects.get(pk=response.data['id'])
    if name == 'expire':
        match.expires_at = timezone.now() - timedelta(seconds=1)
        match.save()
        response = action(client, dmitry, match, 'accept')
        assert response.data['status'] == 'expired'
    else:
        response = action(client, bucky if name == 'cancel' else dmitry, match, name)
    assert response.status_code == 200
    sweep_reversi_matches()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert match.ledger_entries.filter(action='refund').count() == 1
    match.refresh_from_db()
    assert match.settled and match.status != 'pending'
    assert action(client, dmitry, match, 'accept').status_code == 409
    # A challenge that never started stays between its two members.
    for viewer in (baker.make('users.User'), None):
        client.force_authenticate(viewer)
        assert client.get(f'{BASE}/{match.id}').status_code == 404
        assert client.get(BASE).data['count'] == 0
    client.force_authenticate(dmitry)
    assert client.get(f'{BASE}/{match.id}').data['status'] == match.status


def test_only_the_right_player_answers_a_challenge(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = ReversiMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'accept').status_code == 403
    assert action(client, bucky, match, 'decline').status_code == 403
    assert action(client, dmitry, match, 'cancel').status_code == 403
    assert action(client, bucky, match, 'move', row=2, column=3).status_code == 409
    assert action(client, bucky, match, 'resign').status_code == 409
    assert action(client, baker.make('users.User'), match, 'accept').status_code == 404
    assert action(client, dmitry, match, 'accept').status_code == 200
    match.refresh_from_db()
    assert action(client, dmitry, match, 'accept').status_code == 409


def test_pending_challenges_are_private_and_started_matches_are_public(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = ReversiMatch.objects.get(pk=response.data['id'])
    stranger = baker.make('users.User')
    for viewer in (stranger, None):
        client.force_authenticate(viewer)
        assert client.get(BASE).data['count'] == 0
        assert client.get(f'{BASE}/{match.id}').status_code == 404
    assert action(client, dmitry, match, 'accept').status_code == 200
    match.refresh_from_db()
    for viewer in (stranger, None):
        client.force_authenticate(viewer)
        listed = client.get(BASE, {'mine': 'exclude', 'status': 'active'}).data
        assert [row['id'] for row in listed['results']] == [match.id]
        assert 'legal_moves' not in listed['results'][0]
        detail = client.get(f'{BASE}/{match.id}')
        assert detail.status_code == 200
        assert detail.data['legal_moves'] == [[2, 3], [3, 2], [4, 5], [5, 4]]
    assert action(client, stranger, match, 'move', row=2, column=3).status_code == 403
    client.force_authenticate(bucky)
    assert client.get(BASE, {'mine': 'true'}).data['count'] == 1
    assert client.get(BASE, {'mine': 'exclude'}).data['count'] == 0
    assert client.get(BASE, {'mine': 'true', 'status': 'pending,finished'}).data['count'] == 0


@pytest.mark.parametrize(
    'query,count',
    [
        ({'status': '\x00'}, 0),
        ({'status': 'a\x00b,active'}, 1),
        ({'status': 'unknown'}, 0),
        ({'status': 'active,finished'}, 1),
        ({'mine': '\x00'}, 1),
        ({'page_size': '\x00'}, 1),
    ],
)
def test_list_filters_ignore_values_the_database_would_reject(client, bucky, query, count):
    computer_match(client, bucky)
    client.force_authenticate(None)
    response = client.get(BASE, query)
    assert response.status_code == 200
    assert response.data['count'] == count


def test_admin_is_view_only():
    from django.contrib import admin

    from thenewboston.reversi.admin import ReversiMatchAdmin

    model_admin = ReversiMatchAdmin(ReversiMatch, admin.site)
    assert not model_admin.has_add_permission(None)
    assert not model_admin.has_change_permission(None)
    assert not model_admin.has_delete_permission(None)


def test_turns_alternate_and_illegal_or_stale_moves_change_nothing(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    assert action(client, dmitry, match, 'move', row=2, column=4).status_code == 403
    assert action(client, bucky, match, 'move', row=0, column=0).status_code == 400
    assert action(client, bucky, match, 'move', row=3, column=3).status_code == 400
    assert action(client, bucky, match, 'move', row=8, column=0).status_code == 400
    assert action(client, bucky, match, 'move', row=2).status_code == 400
    match.refresh_from_db()
    assert (match.version, match.move_count, match.board) == (2, 0, initial_board())
    stale_version = match.version
    response = move(client, bucky, match, 2, 3)
    assert response.status_code == 200
    assert response.data['last_move'] == {'side': 'black', 'row': 2, 'column': 3, 'flipped': [[3, 3]], 'passed': None}
    assert response.data['active_side'] == 'white'
    assert response.data['scores'] == {'black': 4, 'white': 1}
    assert response.data['legal_moves'] == [[2, 2], [2, 4], [4, 2]]
    client.force_authenticate(bucky)
    stale = client.post(f'{BASE}/{match.id}/move', {'expected_version': stale_version, 'row': 4, 'column': 5})
    assert stale.status_code == 409
    assert move(client, dmitry, match, 2, 2).status_code == 200
    assert match.active_side == 'black'
    assert match.move_count == 2
    assert [event.event_type for event in match.events.all()] == ['created', 'accepted', 'move', 'move']


def test_a_player_without_a_move_passes_automatically(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    set_board(match, PASS_BOARD)
    response = move(client, bucky, match, 0, 0)
    assert response.status_code == 200
    assert response.data['last_move']['passed'] == 'white'
    assert response.data['active_side'] == 'black'
    assert response.data['status'] == 'active'
    assert action(client, dmitry, match, 'move', row=7, column=5).status_code == 403
    response = move(client, bucky, match, 7, 5)
    assert response.data['status'] == 'finished'
    assert (response.data['winner'], response.data['result_reason']) == ('black', 'disk_count')
    assert response.data['scores'] == {'black': 6, 'white': 0}
    assert response.data['active_side'] is None and response.data['legal_moves'] == []


@pytest.mark.parametrize(
    'black_rows,winner,reason,balances',
    [(5, 'black', 'disk_count', (1100, 900)), (3, 'white', 'disk_count', (900, 1100)), (4, None, 'draw', (1000, 1000))],
)
def test_final_count_pays_the_winner_and_a_draw_returns_both_stakes(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet, black_rows, winner, reason, balances
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    assert match.prize_pool_total == 200
    set_board(match, full_board(black_rows))
    response = move(client, bucky, match, 0, 0)
    assert response.status_code == 200, response.data
    assert (response.data['status'], response.data['winner'], response.data['result_reason']) == (
        'finished',
        winner,
        reason,
    )
    assert response.data['computer_reward'] is None
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == balances
    assert match.settled
    settlement = match.ledger_entries.exclude(action='stake')
    assert sorted(settlement.values_list('action', 'amount')) == (
        [('payout', 200)] if winner else [('refund', 100), ('refund', 100)]
    )
    assert action(client, bucky, match, 'resign').status_code == 409
    assert action(client, bucky, match, 'move', row=0, column=0).status_code == 409


def test_resignation_pays_the_opponent_whatever_the_board_says(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    assert move(client, bucky, match, 2, 3).status_code == 200
    response = action(client, bucky, match, 'resign')
    assert (response.data['winner'], response.data['result_reason']) == ('white', 'resignation')
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (900, 1100)


def test_a_fallen_clock_loses_on_the_next_action_read_or_sweep(
    client, bucky, dmitry, dmitry_tnb_wallet, bucky_tnb_wallet
):
    for trigger in ('move', 'read', 'sweep'):
        match = accepted_match(client, bucky, dmitry, stake_amount=10)
        match.clock_black_ms = 1000
        match.turn_started_at = timezone.now() - timedelta(seconds=2)
        match.save()
        if trigger == 'move':
            response = action(client, bucky, match, 'move', row=2, column=3)
            assert response.status_code == 200
        elif trigger == 'read':
            client.force_authenticate(None)
            response = client.get(f'{BASE}/{match.id}')
            assert response.data['status'] == 'finished'
        else:
            sweep_reversi_matches()
        match.refresh_from_db()
        assert (match.status, match.winner, match.result_reason) == ('finished', 'white', 'timeout')
        assert match.clock_black_ms == 0 and match.move_count == 0
        assert match.events.filter(event_type='timeout').count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    bucky_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (970, 1030)


def test_thinking_time_comes_off_the_mover_clock(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry, time_limit_seconds=300)
    match.turn_started_at = timezone.now() - timedelta(seconds=30)
    match.save()
    assert move(client, bucky, match, 2, 3).status_code == 200
    assert 269000 <= match.clock_black_ms <= 270000
    assert match.clock_white_ms == 300000


def test_rematch_swaps_colors_keeps_terms_and_is_created_once(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100, time_limit_seconds=600)
    assert action(client, bucky, match, 'rematch').status_code == 409
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    response = action(client, dmitry, match, 'rematch')
    assert response.status_code == 200
    rematch = ReversiMatch.objects.get(pk=response.data['id'])
    assert rematch.id != match.id and rematch.rematch_of_id == match.id
    assert (rematch.host, rematch.guest, rematch.status) == (dmitry, bucky, 'pending')
    assert (rematch.stake_amount, rematch.time_limit_seconds) == (100, 600)
    # dmitry had white, so the rematch gives dmitry black.
    assert rematch.host_side == 'black'
    assert action(client, bucky, match, 'rematch').data['id'] == rematch.id
    assert ReversiMatch.objects.count() == 2
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1100 - 100


def test_computer_rematch_keeps_color_and_difficulty(client, bucky):
    match = computer_match(client, bucky, color='white', difficulty='easy')
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    response = action(client, bucky, match, 'rematch')
    assert (response.data['host_side'], response.data['difficulty'], response.data['status']) == (
        'white',
        'easy',
        'active',
    )
    assert response.data['id'] != match.id


def test_computer_replies_and_moves_again_when_the_player_must_pass(client, bucky, computer_queue):
    match = computer_match(client, bucky)
    assert move(client, bucky, match, 2, 3).status_code == 200
    computer_queue.assert_called_with(match)
    version = match.version
    run_computer(match.pk, version)
    match.refresh_from_db()
    assert match.active_side == 'black' and match.move_count == 2
    assert match.last_move['side'] == 'white'
    # A repeated or late delivery of the same task does nothing.
    run_computer(match.pk, version)
    match.refresh_from_db()
    assert match.move_count == 2

    set_board(match, WHITE_PASS_BOARD, 'white')
    computer_queue.reset_mock()
    run_computer(match.pk, match.version)
    match.refresh_from_db()
    assert match.last_move['passed'] == 'black'
    assert match.active_side == 'white' and match.status == 'active'
    computer_queue.assert_called_once()
    run_computer(match.pk, match.version)
    match.refresh_from_db()
    assert (match.status, match.winner, match.result_reason) == ('finished', 'white', 'disk_count')
    assert match.computer_reward == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}


def test_computer_turn_is_queued_after_commit_and_survives_a_broker_outage(client, bucky):
    match = computer_match(client, bucky, color='white')
    with patch('thenewboston.reversi.tasks.play_computer_turn.delay') as delay:
        enqueue_computer(match)
        delay.assert_called_once_with(match.id, match.version)
        delay.reset_mock()
        sweep_reversi_matches()
        delay.assert_called_once_with(match.id, match.version)
    with patch('thenewboston.reversi.tasks.play_computer_turn.delay', side_effect=OSError('broker down')):
        enqueue_computer(match)
    match.active_side = 'white'
    match.save()
    with patch('thenewboston.reversi.tasks.play_computer_turn.delay') as delay:
        enqueue_computer(match)
        delay.assert_not_called()


def test_computer_win_pays_the_game_fund_reward_once(client, bucky, bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=25, request_id=uuid4())
    match = computer_match(client, bucky)
    set_board(match, PASS_BOARD)
    assert move(client, bucky, match, 0, 0).data['computer_reward'] is None
    response = move(client, bucky, match, 7, 5)
    assert response.status_code == 200, response.data
    assert response.data['computer_reward'] == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
    assert client.get(f'{BASE}/{match.id}').data['computer_reward']['amount'] == 10
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010
    assert GameFund.objects.get().balance == 15
    assert GameRewardDecision.objects.get().game == 'reversi'
    assert ReversiLedgerEntry.objects.count() == 0


@pytest.mark.parametrize('ending', ['resign', 'timeout', 'draw', 'loss'])
def test_only_a_completed_win_over_the_computer_earns_a_reward(
    client, bucky, bucky_tnb_wallet, dmitry_tnb_wallet, ending
):
    contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())
    match = computer_match(client, bucky)
    if ending == 'resign':
        response = action(client, bucky, match, 'resign')
    elif ending == 'timeout':
        # The computer's flag falls: the player wins, but not by finishing the game.
        match.active_side = 'white'
        match.clock_white_ms = 1
        match.turn_started_at = timezone.now() - timedelta(seconds=1)
        match.save()
        client.force_authenticate(bucky)
        response = client.get(f'{BASE}/{match.id}')
        assert response.data['winner'] == 'black'
    else:
        set_board(match, full_board(4 if ending == 'draw' else 3))
        response = move(client, bucky, match, 0, 0)
    assert response.status_code == 200
    assert response.data['status'] == 'finished'
    assert response.data['computer_reward'] == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert GameFund.objects.get().balance == 10


def test_win_with_an_empty_fund_is_recorded_without_payment(client, bucky, bucky_tnb_wallet):
    match = computer_match(client, bucky)
    set_board(match, full_board(5))
    response = move(client, bucky, match, 0, 0)
    assert response.data['computer_reward'] == {'status': 'fund_empty', 'amount': 0, 'currency': 'TNB'}
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
