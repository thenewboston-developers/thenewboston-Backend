from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.game_rewards.services import contribute
from thenewboston.hex.models import HexEvent, HexLedgerEntry, HexMatch
from thenewboston.hex.rules import BLUE, EMPTY, RED, SIZES, empty_board
from thenewboston.hex.services import queue_computer as enqueue_computer, run_computer
from thenewboston.hex.tasks import sweep_hex_matches
from thenewboston.hex.tests.test_rules import board_with, column, row_cells
from thenewboston.notifications.models import Notification

BASE = '/api/hex/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.hex.services.queue_computer') as queue:
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


def accepted_match(client, red, blue, **kwargs):
    response = create(client, red, blue, **kwargs)
    assert response.status_code == 201, response.data
    match = HexMatch.objects.get(pk=response.data['id'])
    response = action(client, blue, match, 'accept')
    assert response.status_code == 200, response.data
    match.refresh_from_db()
    return match


def one_stone_from_winning(match, side='red'):
    """Leave a side one stone short of its edge; returns the cell that completes the chain."""
    size = match.board_size
    if side == 'red':
        match.board = board_with(size, red=column(size, 3, range(size - 1)), blue=row_cells(size, size - 1, range(2)))
        match.active_side, cell = 'red', (size - 1) * size + 3
    else:
        match.board = board_with(size, blue=row_cells(size, 3, range(size - 1)), red=column(size, size - 1, range(2)))
        match.active_side, cell = 'blue', 3 * size + size - 1
    match.move_count = size + 1
    match.save()
    return cell


def test_free_computer_match_needs_no_wallet(client, bucky):
    response = create(client, bucky)
    assert response.status_code == 201
    assert response.data['status'] == 'active'
    assert response.data['blue'] is None
    assert response.data['computer_name'] == 'Computer'
    assert response.data['your_side'] == response.data['active_side'] == 'red'
    assert response.data['board_size'] == 11 and response.data['board'] == empty_board(11)
    assert response.data['move_count'] == 0 and response.data['can_swap'] is False
    assert response.data['winning_path'] is None and response.data['last_move'] is None
    assert not HexLedgerEntry.objects.exists()


@pytest.mark.parametrize('size', SIZES)
def test_board_size_is_chosen_at_creation(client, bucky, size):
    response = create(client, bucky, board_size=size)
    assert response.status_code == 201, response.data
    assert response.data['board_size'] == size and response.data['board'] == [EMPTY] * (size * size)
    match = HexMatch.objects.get(pk=response.data['id'])
    last = size * size - 1
    assert action(client, bucky, match, 'move', cell=last + 1).status_code == 400
    response = action(client, bucky, match, 'move', cell=last)
    assert response.status_code == 200, response.data
    assert response.data['board'][last] == RED


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
        {'board_size': 8},
        {'board_size': 19},
    ],
)
def test_invalid_creation_does_not_charge(client, bucky, payload):
    assert create(client, bucky, **payload).status_code == 400
    assert not HexMatch.objects.exists()


def test_authentication_self_challenge_and_public_read(client, bucky):
    assert client.get(BASE).status_code == 200
    assert client.post(BASE, {'mode': 'computer'}, format='json').status_code == 401
    assert create(client, bucky, bucky).status_code == 400


def test_insufficient_funds_creation_and_accept_are_atomic(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    assert create(client, bucky, dmitry, stake_amount=1001).status_code == 400
    assert not HexMatch.objects.exists()
    response = create(client, bucky, dmitry, stake_amount=100)
    match = HexMatch.objects.get(pk=response.data['id'])
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
    assert create(client, bucky, dmitry, stake_amount=100, board_size=9, request_id=request_id).status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900
    assert HexLedgerEntry.objects.count() == 1
    notification = Notification.objects.get(payload__notification_type='HEX_CHALLENGE')
    assert notification.owner == dmitry
    assert notification.payload['challenger']['username'] == 'bucky'
    assert notification.payload['match_id'] == first.data['id']
    assert (notification.payload['board_size'], notification.payload['stake_amount']) == (11, 100)


@pytest.mark.parametrize('name', ['cancel', 'decline', 'expire'])
def test_pending_challenge_refunds_exactly_once(client, bucky, dmitry, bucky_tnb_wallet, name):
    response = create(client, bucky, dmitry, stake_amount=100)
    match = HexMatch.objects.get(pk=response.data['id'])
    if name == 'expire':
        match.expires_at = timezone.now() - timedelta(seconds=1)
        match.save()
        response = action(client, dmitry, match, 'accept')
        assert response.data['status'] == 'expired'
    else:
        response = action(client, bucky if name == 'cancel' else dmitry, match, name)
    assert response.status_code == 200
    sweep_hex_matches()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert match.ledger_entries.filter(action='refund').count() == 1


def test_sweep_expires_unanswered_challenges(client, bucky, dmitry, bucky_tnb_wallet):
    response = create(client, bucky, dmitry, stake_amount=100)
    HexMatch.objects.filter(pk=response.data['id']).update(expires_at=timezone.now() - timedelta(seconds=1))
    sweep_hex_matches()
    sweep_hex_matches()
    match = HexMatch.objects.get(pk=response.data['id'])
    bucky_tnb_wallet.refresh_from_db()
    assert match.status == 'expired' and match.settled and bucky_tnb_wallet.balance == 1000


def test_pending_invitations_private_and_only_participants_can_mutate(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = HexMatch.objects.get(pk=response.data['id'])
    stranger = baker.make('users.User')
    client.force_authenticate(stranger)
    assert client.get(BASE).data['count'] == 0
    assert client.get(f'{BASE}/{match.id}').status_code == 404
    assert action(client, bucky, match, 'accept').status_code == 403
    assert action(client, dmitry, match, 'cancel').status_code == 403
    assert action(client, dmitry, match, 'accept').status_code == 200
    match.refresh_from_db()
    client.force_authenticate(stranger)
    assert client.get(f'{BASE}/{match.id}').data['your_side'] is None
    assert action(client, stranger, match, 'resign').status_code == 403
    assert action(client, stranger, match, 'move', cell=0).status_code == 403
    client.force_authenticate(None)
    assert client.get(f'{BASE}/{match.id}').status_code == 200
    assert client.get(f'{BASE}?mine=true').data['count'] == 0
    assert action(client, None, match, 'move', cell=0).status_code == 401


def test_turns_stale_versions_and_invalid_moves(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    assert action(client, dmitry, match, 'move', cell=60).status_code == 403
    for cell in (-1, 121, 168, 169, 'a', None, 1.5):
        assert action(client, bucky, match, 'move', cell=cell).status_code == 400
    assert action(client, bucky, match, 'move').status_code == 400
    response = action(client, bucky, match, 'move', cell=60)
    assert response.status_code == 200
    assert response.data['last_move'] == {'side': 'red', 'cell': 60, 'swap': False}
    assert response.data['board'][60] == RED and response.data['board'].count(EMPTY) == 120
    assert response.data['active_side'] == 'blue' and response.data['move_count'] == 1
    assert action(client, bucky, match, 'move', cell=61).status_code == 409
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', cell=61).status_code == 403
    response = action(client, dmitry, match, 'move', cell=60)
    assert response.status_code == 400 and 'already taken' in str(response.data)
    response = action(client, dmitry, match, 'move', cell=61)
    assert response.data['board'][61] == BLUE and response.data['active_side'] == 'red'
    assert list(HexEvent.objects.filter(match=match).values_list('event_type', flat=True)) == [
        'created',
        'accepted',
        'move',
        'move',
    ]


@pytest.mark.parametrize('side', ['red', 'blue'])
def test_connection_pays_both_stakes_to_the_winner_once(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet, side
):
    match = accepted_match(client, bucky, dmitry, stake_amount=123, board_size=7)
    cell = one_stone_from_winning(match, side)
    winner = bucky if side == 'red' else dmitry
    response = action(client, winner, match, 'move', cell=cell)
    assert response.status_code == 200, response.data
    assert response.data['status'] == 'finished' and response.data['winner'] == side
    assert response.data['result_reason'] == 'connection' and response.data['active_side'] != side
    expected = column(7, 3) if side == 'red' else row_cells(7, 3)
    assert response.data['winning_path'] == expected
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    balances = (1123, 877) if side == 'red' else (877, 1123)
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == balances
    assert sum(match.ledger_entries.values_list('amount', flat=True)) == 0
    sweep_hex_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1
    assert action(client, winner, match, 'move', cell=cell).status_code == 409
    match.refresh_from_db()
    assert action(client, winner, match, 'move', cell=0).status_code == 409
    assert action(client, winner, match, 'resign').status_code == 409


def test_resignation_pays_the_opponent(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=50)
    response = action(client, dmitry, match, 'resign')
    assert (response.data['status'], response.data['winner'], response.data['result_reason']) == (
        'finished',
        'red',
        'resignation',
    )
    assert response.data['winning_path'] is None
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1050, 950)


def test_blue_can_swap_the_opening_stone_once(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    client.force_authenticate(dmitry)
    assert client.get(f'{BASE}/{match.id}').data['can_swap'] is False
    assert action(client, dmitry, match, 'swap').status_code == 403
    assert action(client, bucky, match, 'swap').status_code == 400
    assert action(client, bucky, match, 'move', cell=2 * 11 + 7).status_code == 200
    match.refresh_from_db()
    client.force_authenticate(dmitry)
    assert client.get(f'{BASE}/{match.id}').data['can_swap'] is True
    assert [item['can_swap'] for item in client.get(BASE).data['results']] == [False]
    client.force_authenticate(bucky)
    assert client.get(f'{BASE}/{match.id}').data['can_swap'] is False
    assert action(client, bucky, match, 'swap').status_code == 403
    response = action(client, dmitry, match, 'swap')
    assert response.status_code == 200, response.data
    mirrored = 7 * 11 + 2
    assert response.data['board'] == board_with(11, blue=[mirrored])
    assert response.data['last_move'] == {'side': 'blue', 'cell': mirrored, 'swap': True, 'from': 2 * 11 + 7}
    assert response.data['active_side'] == 'red' and response.data['move_count'] == 2
    assert response.data['can_swap'] is False
    match.refresh_from_db()
    assert match.clock_blue_ms <= 900000 and match.events.filter(event_type='swap').count() == 1
    assert action(client, bucky, match, 'swap').status_code == 400
    assert action(client, bucky, match, 'move', cell=0).status_code == 200
    match.refresh_from_db()
    assert action(client, dmitry, match, 'swap').status_code == 400


def test_blue_may_also_answer_the_opening_with_a_stone(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    action(client, bucky, match, 'move', cell=60)
    match.refresh_from_db()
    response = action(client, dmitry, match, 'move', cell=61)
    assert response.status_code == 200 and response.data['move_count'] == 2
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', cell=62).status_code == 200
    match.refresh_from_db()
    # It is Blue's turn again, but the chance to swap ended with Blue's first reply.
    client.force_authenticate(dmitry)
    detail = client.get(f'{BASE}/{match.id}').data
    assert detail['active_side'] == 'blue' and detail['can_swap'] is False
    assert action(client, dmitry, match, 'swap').status_code == 400


def test_the_opening_cannot_be_swapped_in_a_computer_game(client, bucky):
    response = create(client, bucky)
    match = HexMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'swap').status_code == 400
    response = action(client, bucky, match, 'move', cell=60)
    assert response.data['can_swap'] is False
    match.refresh_from_db()
    assert action(client, bucky, match, 'swap').status_code == 403
    run_computer(match.id, match.version)
    match.refresh_from_db()
    assert match.board[60] == RED and match.board.count(BLUE) == 1 and match.last_move['swap'] is False


def test_timeout_from_retrieve_settles_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    match.clock_red_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    client.force_authenticate(bucky)
    response = client.get(f'{BASE}/{match.id}')
    assert response.data['winner'] == 'blue'
    assert response.data['result_reason'] == 'timeout'
    assert response.data['clock_red_ms'] == 0
    sweep_hex_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1100


def test_clocks_only_charge_the_player_to_move(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry, time_limit_seconds=300)
    assert (match.clock_red_ms, match.clock_blue_ms) == (300000, 300000)
    match.turn_started_at = timezone.now() - timedelta(seconds=10)
    match.save()
    response = action(client, bucky, match, 'move', cell=60)
    assert 289000 <= response.data['clock_red_ms'] <= 290000
    assert response.data['clock_blue_ms'] == 300000


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_cpu_moves_once_and_stale_tasks_are_noop(client, bucky, difficulty):
    response = create(client, bucky, difficulty=difficulty)
    match = HexMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'move', cell=60).status_code == 200
    match.refresh_from_db()
    version = match.version
    run_computer(match.id, version - 1)
    match.refresh_from_db()
    assert match.active_side == 'blue'
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.active_side == 'red' and match.version == version + 1
    assert match.board.count(BLUE) == 1 and match.board[60] == RED and match.move_count == 2
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.version == version + 1


def test_computer_is_queued_after_the_players_move_and_never_for_a_human_match(client, bucky, dmitry, computer_queue):
    response = create(client, bucky)
    match = HexMatch.objects.get(pk=response.data['id'])
    action(client, bucky, match, 'move', cell=60)
    assert computer_queue.call_args.args[0].id == match.id
    with patch('thenewboston.hex.tasks.play_computer_turn.delay') as delay:
        human = accepted_match(client, bucky, dmitry)
        enqueue_computer(human)
        match.refresh_from_db()
        match.active_side = 'red'
        enqueue_computer(match)
        assert not delay.called


def test_cpu_queue_recovers_after_broker_failure(client, bucky):
    response = create(client, bucky)
    match = HexMatch.objects.get(pk=response.data['id'])
    action(client, bucky, match, 'move', cell=60)
    match.refresh_from_db()
    with patch('thenewboston.hex.tasks.play_computer_turn.delay', side_effect=[ConnectionError, None]) as delay:
        enqueue_computer(match)
        sweep_hex_matches()
        assert delay.call_count == 2
        assert all(call.args == (match.id, match.version) for call in delay.call_args_list)


def test_rematch_preserves_terms_and_requires_acceptance(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100, time_limit_seconds=600, board_size=9)
    assert action(client, bucky, match, 'rematch').status_code == 409
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    first = action(client, dmitry, match, 'rematch')
    second = action(client, bucky, match, 'rematch')
    assert first.status_code == second.status_code == 200
    assert first.data['id'] == second.data['id'] != match.id
    # The player who asks for the rematch moves first in it.
    assert first.data['your_side'] == 'red' and second.data['your_side'] == 'blue'
    assert first.data['status'] == 'pending' and first.data['stake_amount'] == 100
    assert first.data['time_limit_seconds'] == 600 and first.data['rematch_of'] == match.id
    assert first.data['board_size'] == 9 and first.data['board'] == empty_board(9)
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000 + 100 - 100


def test_computer_win_reward_paid_once(client, bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = create(client, bucky_tnb_wallet.owner, board_size=7)
    match = HexMatch.objects.get(pk=response.data['id'])
    cell = one_stone_from_winning(match)
    response = action(client, bucky_tnb_wallet.owner, match, 'move', cell=cell)
    assert response.data['computer_reward'] == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
    assert response.data['winner'] == 'red' and response.data['result_reason'] == 'connection'
    sweep_hex_matches()
    assert action(client, bucky_tnb_wallet.owner, match, 'move', cell=cell).status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010 and GameFund.objects.get().balance == 10
    assert GameRewardDecision.objects.filter(game='hex', match_id=match.id).count() == 1
    assert not match.ledger_entries.exists()


def test_computer_win_with_an_empty_fund_is_recorded_and_never_paid_later(client, bucky_tnb_wallet, dmitry_tnb_wallet):
    response = create(client, bucky_tnb_wallet.owner, board_size=7)
    match = HexMatch.objects.get(pk=response.data['id'])
    response = action(client, bucky_tnb_wallet.owner, match, 'move', cell=one_stone_from_winning(match))
    assert response.data['computer_reward'] == {'status': 'fund_empty', 'amount': 0, 'currency': 'TNB'}
    contribute(user=dmitry_tnb_wallet.owner, amount=100, request_id=uuid4())
    assert client.get(f'{BASE}/{match.id}').data['computer_reward']['status'] == 'fund_empty'
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 and GameFund.objects.get().balance == 100


@pytest.mark.parametrize('result', ['computer_connects', 'resign', 'computer_timeout', 'player_timeout'])
def test_computer_nonwins_never_receive_rewards(client, bucky_tnb_wallet, dmitry_tnb_wallet, result):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = create(client, bucky_tnb_wallet.owner, board_size=7)
    match = HexMatch.objects.get(pk=response.data['id'])
    if result == 'computer_connects':
        one_stone_from_winning(match, 'blue')
        run_computer(match.id, match.version)
        response = client.get(f'{BASE}/{match.id}')
        assert (response.data['winner'], response.data['result_reason']) == ('blue', 'connection')
        assert response.data['winning_path'][0] % 7 == 0 and response.data['winning_path'][-1] % 7 == 6
    elif result == 'resign':
        response = action(client, bucky_tnb_wallet.owner, match, 'resign')
    else:
        match.active_side = 'blue' if result == 'computer_timeout' else 'red'
        match.turn_started_at = timezone.now() - timedelta(seconds=1000)
        match.save()
        response = client.get(f'{BASE}/{match.id}')
        assert response.data['winner'] == ('red' if result == 'computer_timeout' else 'blue')
    assert response.data['status'] == 'finished'
    assert response.data['computer_reward'] == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 and GameFund.objects.get().balance == 20


def test_clock_expiring_during_validation_cannot_accept_a_late_move(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    start = timezone.now()
    match.turn_started_at = start
    match.clock_red_ms = 1000
    match.save()
    with patch(
        'thenewboston.hex.services.timezone.now',
        side_effect=[
            start + timedelta(milliseconds=999),
            start + timedelta(milliseconds=1001),
            *[start + timedelta(milliseconds=1002)] * 20,
        ],
    ):
        response = action(client, bucky, match, 'move', cell=60)
    assert response.status_code == 200
    assert response.data['result_reason'] == 'timeout' and response.data['winner'] == 'blue'
    assert response.data['board'] == empty_board(11) and response.data['last_move'] is None


def test_lists_filter_by_participant_and_status(client, bucky, dmitry):
    active = accepted_match(client, bucky, dmitry)
    finished = accepted_match(client, bucky, dmitry)
    action(client, bucky, finished, 'resign')
    stranger = baker.make('users.User')
    client.force_authenticate(bucky)
    assert {item['id'] for item in client.get(f'{BASE}?mine=1').data['results']} == {active.id, finished.id}
    assert [item['id'] for item in client.get(f'{BASE}?mine=1&status=pending,active').data['results']] == [active.id]
    assert client.get(f'{BASE}?mine=exclude').data['count'] == 0
    client.force_authenticate(stranger)
    assert client.get(f'{BASE}?mine=1').data['count'] == 0
    assert client.get(f'{BASE}?mine=exclude&status=finished').data['count'] == 1
