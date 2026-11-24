from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib import admin
from django.test import Client
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.dots_and_boxes.models import DotsAndBoxesEvent, DotsAndBoxesLedgerEntry, DotsAndBoxesMatch
from thenewboston.dots_and_boxes.rules import line_count
from thenewboston.dots_and_boxes.services import queue_computer as enqueue_computer, run_computer
from thenewboston.dots_and_boxes.tasks import sweep_dots_and_boxes_matches
from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.game_rewards.services import contribute
from thenewboston.notifications.models import Notification

BASE = '/api/dots-and-boxes/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.dots_and_boxes.services.queue_computer') as queue:
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


def accepted_match(client, blue, red, **kwargs):
    response = create(client, blue, red, **kwargs)
    assert response.status_code == 201, response.data
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    response = action(client, red, match, 'accept')
    assert response.status_code == 200, response.data
    match.refresh_from_db()
    return match


def one_line_left(match, *, blue, red, active='blue'):
    """Leave only the right edge of the last box open, with every other box already claimed."""
    last = line_count(match.board_size) - 1
    assert blue + red == match.board_size**2 - 1
    match.lines = [1] * last + [0]
    match.boxes = [1] * blue + [2] * red + [0]
    match.score_blue, match.score_red = blue, red
    match.moves = list(range(last))
    match.active_side = active
    match.save()
    return last


def corridors(match, active='red'):
    """Draw every horizontal line: each row becomes a chain, and no safe line is left."""
    horizontals = match.board_size * (match.board_size + 1)
    match.lines = [1] * horizontals + [0] * horizontals
    match.moves = list(range(horizontals))
    match.active_side = active
    match.save()
    return horizontals


def test_free_computer_match_needs_no_wallet(client, bucky):
    response = create(client, bucky)
    assert response.status_code == 201
    assert response.data['status'] == 'active'
    assert response.data['red'] is None
    assert response.data['computer_name'] == 'Computer'
    assert response.data['your_side'] == 'blue' and response.data['active_side'] == 'blue'
    assert response.data['board_size'] == 4
    assert response.data['lines'] == [0] * 40 and response.data['boxes'] == [0] * 16
    assert response.data['moves'] == []
    assert (response.data['score_blue'], response.data['score_red']) == (0, 0)
    assert not DotsAndBoxesLedgerEntry.objects.exists()


@pytest.mark.parametrize('size,lines', [(3, 24), (4, 40), (5, 60)])
def test_each_board_size_starts_with_the_right_number_of_lines(client, bucky, size, lines):
    response = create(client, bucky, board_size=size)
    assert response.status_code == 201, response.data
    assert len(response.data['lines']) == lines and len(response.data['boxes']) == size * size


@pytest.mark.parametrize(
    'payload',
    [
        {'mode': 'human'},
        {'stake_amount': 1},
        {'time_limit_seconds': 1},
        {'difficulty': 'impossible'},
        {'board_size': 2},
        {'board_size': 6},
        {'stake_amount': -1},
        {'stake_amount': 1000000001},
        {'request_id': 'no'},
    ],
)
def test_invalid_creation_does_not_charge(client, bucky, payload):
    assert create(client, bucky, **payload).status_code == 400
    assert not DotsAndBoxesMatch.objects.exists()


def test_authentication_self_challenge_and_public_read(client, bucky):
    assert client.get(BASE).status_code == 200
    assert client.post(BASE, {'mode': 'computer'}, format='json').status_code == 401
    assert create(client, bucky, bucky).status_code == 400


def test_insufficient_funds_creation_and_accept_are_atomic(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    assert create(client, bucky, dmitry, stake_amount=1001).status_code == 400
    assert not DotsAndBoxesMatch.objects.exists()
    response = create(client, bucky, dmitry, stake_amount=100)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
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
    assert create(client, bucky, dmitry, stake_amount=100, board_size=5, request_id=request_id).status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 900
    assert DotsAndBoxesLedgerEntry.objects.count() == 1
    notifications = Notification.objects.filter(payload__notification_type='DOTS_AND_BOXES_CHALLENGE')
    assert notifications.count() == 1
    assert notifications.get().owner == dmitry
    assert notifications.get().payload['board_size'] == 4 and notifications.get().payload['stake_amount'] == 100


@pytest.mark.parametrize('name', ['cancel', 'decline', 'expire'])
def test_pending_challenge_refunds_exactly_once(client, bucky, dmitry, bucky_tnb_wallet, name):
    response = create(client, bucky, dmitry, stake_amount=100)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    if name == 'expire':
        match.expires_at = timezone.now() - timedelta(seconds=1)
        match.save()
        response = action(client, dmitry, match, 'accept')
        assert response.data['status'] == 'expired'
    else:
        response = action(client, bucky if name == 'cancel' else dmitry, match, name)
    assert response.status_code == 200
    sweep_dots_and_boxes_matches()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert match.ledger_entries.filter(action='refund').count() == 1


def test_sweep_expires_an_unanswered_challenge_and_refunds_it(client, bucky, dmitry, bucky_tnb_wallet):
    response = create(client, bucky, dmitry, stake_amount=100)
    DotsAndBoxesMatch.objects.filter(pk=response.data['id']).update(expires_at=timezone.now() - timedelta(seconds=1))
    sweep_dots_and_boxes_matches()
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    bucky_tnb_wallet.refresh_from_db()
    assert match.status == 'expired' and match.settled and bucky_tnb_wallet.balance == 1000


def test_pending_invitations_private_and_only_participants_can_mutate(client, bucky, dmitry):
    response = create(client, bucky, dmitry)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
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
    assert action(client, stranger, match, 'move', line=0).status_code == 403
    assert action(client, stranger, match, 'resign').status_code == 403
    client.force_authenticate(None)
    assert client.get(f'{BASE}/{match.id}').status_code == 200
    assert client.get(f'{BASE}?mine=true').data['count'] == 0


def test_turns_stale_versions_and_invalid_lines(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    assert action(client, dmitry, match, 'move', line=0).status_code == 403
    # 4 by 4 has lines 0 to 39; 60 is beyond any board.
    assert action(client, bucky, match, 'move', line=40).status_code == 400
    assert action(client, bucky, match, 'move', line=60).status_code == 400
    assert action(client, bucky, match, 'move', line='first').status_code == 400
    assert action(client, bucky, match, 'move').status_code == 400
    response = action(client, bucky, match, 'move', line=7)
    assert response.status_code == 200
    assert response.data['lines'][7] == 1 and response.data['moves'] == [7]
    assert response.data['active_side'] == 'red'
    assert action(client, bucky, match, 'move', line=8).status_code == 409
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', line=8).status_code == 403
    assert action(client, dmitry, match, 'move', line=7).status_code == 400
    response = action(client, dmitry, match, 'move', line=8)
    assert response.data['lines'][8] == 2 and response.data['moves'] == [7, 8]
    assert response.data['active_side'] == 'blue'


def test_completing_a_box_scores_and_keeps_the_turn(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry, board_size=3)
    # Blue and red alternate around the top-left box; red is left to draw its fourth side.
    for user, line in [(bucky, 0), (dmitry, 3), (bucky, 12)]:
        assert action(client, user, match, 'move', line=line).status_code == 200
        match.refresh_from_db()
    response = action(client, dmitry, match, 'move', line=13)
    assert response.status_code == 200
    assert response.data['boxes'][0] == 2
    assert (response.data['score_blue'], response.data['score_red']) == (0, 1)
    assert response.data['active_side'] == 'red' and response.data['status'] == 'active'
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', line=1).status_code == 403
    response = action(client, dmitry, match, 'move', line=1)
    assert response.data['active_side'] == 'blue'
    event = DotsAndBoxesEvent.objects.get(match=match, payload__line=13)
    assert event.payload == {'side': 'red', 'line': 13, 'boxes': [0]}


def test_one_line_can_score_two_boxes(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry, board_size=3)
    match.lines = [1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    match.save()
    response = action(client, bucky, match, 'move', line=13)
    assert response.data['boxes'][:2] == [1, 1] and response.data['score_blue'] == 2
    assert response.data['active_side'] == 'blue'


def test_last_box_pays_both_stakes_to_the_winner_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=123, board_size=3)
    last = one_line_left(match, blue=4, red=4)
    response = action(client, bucky, match, 'move', line=last)
    assert response.status_code == 200
    assert response.data['status'] == 'finished' and response.data['winner'] == 'blue'
    assert response.data['result_reason'] == 'completed'
    assert (response.data['score_blue'], response.data['score_red']) == (5, 4)
    assert response.data['active_side'] == 'blue' and response.data['turn_started_at'] is None
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1123, 877)
    assert sum(match.ledger_entries.values_list('amount', flat=True)) == 0
    sweep_dots_and_boxes_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1
    assert action(client, bucky, match, 'move', line=last).status_code == 409
    match.refresh_from_db()
    assert action(client, bucky, match, 'move', line=last).status_code == 409


def test_the_player_with_more_boxes_wins_even_when_the_other_draws_the_last_line(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, stake_amount=50, board_size=3)
    last = one_line_left(match, blue=6, red=2, active='red')
    response = action(client, dmitry, match, 'move', line=last)
    assert response.data['winner'] == 'blue' and (response.data['score_blue'], response.data['score_red']) == (6, 3)
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1050, 950)


def test_equal_boxes_is_a_draw_that_refunds_both_stakes_once(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    last = one_line_left(match, blue=8, red=7, active='red')
    response = action(client, dmitry, match, 'move', line=last)
    assert response.status_code == 200, response.data
    assert response.data['status'] == 'finished' and response.data['winner'] is None
    assert response.data['result_reason'] == 'completed'
    assert (response.data['score_blue'], response.data['score_red']) == (8, 8)
    sweep_dots_and_boxes_matches()
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1000, 1000)
    assert match.ledger_entries.filter(action='refund').count() == 2


def test_resignation_pays_the_opponent(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    response = action(client, bucky, match, 'resign')
    assert response.data['winner'] == 'red' and response.data['result_reason'] == 'resignation'
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1100


def test_timeout_from_retrieve_settles_once(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100)
    match.clock_blue_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    client.force_authenticate(bucky)
    response = client.get(f'{BASE}/{match.id}')
    assert response.data['winner'] == 'red'
    assert response.data['result_reason'] == 'timeout' and response.data['clock_blue_ms'] == 0
    sweep_dots_and_boxes_matches()
    assert match.ledger_entries.filter(action='payout').count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1100


def test_the_clock_keeps_running_for_a_player_who_keeps_the_turn(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry, board_size=3)
    match.lines = [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    match.turn_started_at = timezone.now() - timedelta(seconds=30)
    match.save()
    response = action(client, bucky, match, 'move', line=13)
    assert response.data['active_side'] == 'blue'
    assert 869000 <= response.data['clock_blue_ms'] <= 870000
    assert response.data['clock_red_ms'] == 900000


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_cpu_moves_once_and_stale_tasks_are_noop(client, bucky, difficulty):
    response = create(client, bucky, difficulty=difficulty)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    assert action(client, bucky, match, 'move', line=0).status_code == 200
    match.refresh_from_db()
    version = match.version
    run_computer(match.id, version - 1)
    match.refresh_from_db()
    assert match.active_side == 'red' and match.moves == [0]
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.active_side == 'blue' and match.version == version + 1
    assert len(match.moves) == 2 and match.lines[match.moves[1]] == 2
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.version == version + 1


def test_cpu_keeps_drawing_while_it_completes_boxes_and_records_every_line(client, bucky):
    response = create(client, bucky, difficulty='normal', board_size=3)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    horizontals = corridors(match, active='blue')
    # Blue has to open a chain: the computer takes all three boxes, then opens the next row.
    assert action(client, bucky, match, 'move', line=horizontals).status_code == 200
    match.refresh_from_db()
    version = match.version
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.boxes[:3] == [2, 2, 2] and match.score_red == 3
    assert match.moves[horizontals + 1 : horizontals + 4] == [13, 14, 15]
    assert match.active_side == 'blue' and match.status == 'active'
    assert match.version == version + 4
    events = DotsAndBoxesEvent.objects.filter(match=match, version__gt=version)
    assert [event.payload['boxes'] for event in events] == [[0], [1], [2], []]
    assert all(event.payload['side'] == 'red' for event in events)


def test_cpu_can_finish_the_game_in_one_turn(client, bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = create(client, bucky_tnb_wallet.owner, board_size=3)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    one_line_left(match, blue=4, red=4, active='red')
    run_computer(match.id, match.version)
    match.refresh_from_db()
    assert match.status == 'finished' and match.winner == 'red' and match.score_red == 5
    assert match.computer_reward == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}
    assert GameFund.objects.get().balance == 20


def test_cpu_queue_recovers_after_broker_failure(client, bucky):
    response = create(client, bucky)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    action(client, bucky, match, 'move', line=0)
    match.refresh_from_db()
    with patch(
        'thenewboston.dots_and_boxes.tasks.play_computer_turn.delay', side_effect=[ConnectionError, None]
    ) as delay:
        enqueue_computer(match)
        sweep_dots_and_boxes_matches()
        assert delay.call_count == 2
        assert all(call.args == (match.id, match.version) for call in delay.call_args_list)


def test_cpu_is_queued_after_a_player_line_that_passes_the_turn(client, bucky, computer_queue):
    response = create(client, bucky)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    computer_queue.reset_mock()
    action(client, bucky, match, 'move', line=0)
    match.refresh_from_db()
    assert computer_queue.call_count == 1 and computer_queue.call_args.args[0].pk == match.pk


def test_rematch_preserves_terms_and_requires_acceptance(client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet):
    match = accepted_match(client, bucky, dmitry, stake_amount=100, time_limit_seconds=600, board_size=5)
    assert action(client, bucky, match, 'resign').status_code == 200
    match.refresh_from_db()
    first = action(client, dmitry, match, 'rematch')
    second = action(client, bucky, match, 'rematch')
    assert first.status_code == second.status_code == 200
    assert first.data['id'] == second.data['id']
    assert first.data['your_side'] == 'blue' and second.data['your_side'] == 'red'
    assert first.data['status'] == 'pending' and first.data['stake_amount'] == 100
    assert first.data['time_limit_seconds'] == 600 and first.data['board_size'] == 5
    assert first.data['lines'] == [0] * 60 and first.data['rematch_of'] == match.id


def test_computer_win_reward_paid_once(client, bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = create(client, bucky_tnb_wallet.owner, board_size=3)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    last = one_line_left(match, blue=4, red=4)
    response = action(client, bucky_tnb_wallet.owner, match, 'move', line=last)
    assert response.data['winner'] == 'blue'
    assert response.data['computer_reward'] == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
    sweep_dots_and_boxes_matches()
    assert action(client, bucky_tnb_wallet.owner, match, 'move', line=last).status_code == 409
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010 and GameFund.objects.get().balance == 10
    assert GameRewardDecision.objects.filter(game='dots_and_boxes', match_id=match.id).count() == 1


@pytest.mark.parametrize('result', ['loss', 'draw', 'resign', 'computer_timeout'])
def test_computer_nonwins_never_receive_rewards(client, bucky_tnb_wallet, dmitry_tnb_wallet, result):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = create(client, bucky_tnb_wallet.owner, board_size=4 if result == 'draw' else 3)
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    if result == 'loss':
        last = one_line_left(match, blue=3, red=5)
        response = action(client, bucky_tnb_wallet.owner, match, 'move', line=last)
        assert response.data['winner'] == 'red'
    elif result == 'draw':
        last = one_line_left(match, blue=7, red=8)
        response = action(client, bucky_tnb_wallet.owner, match, 'move', line=last)
        assert response.data['winner'] is None and response.data['status'] == 'finished'
    elif result == 'resign':
        response = action(client, bucky_tnb_wallet.owner, match, 'resign')
    else:
        match.active_side = 'red'
        match.turn_started_at = timezone.now() - timedelta(seconds=1000)
        match.save()
        response = client.get(f'{BASE}/{match.id}')
        assert response.data['winner'] == 'blue' and response.data['result_reason'] == 'timeout'
    assert response.data['computer_reward']['status'] == 'not_eligible'
    assert response.data['computer_reward']['amount'] == 0
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 and GameFund.objects.get().balance == 20


def test_clock_expiring_while_the_line_is_checked_cannot_accept_a_late_move(client, bucky, dmitry):
    match = accepted_match(client, bucky, dmitry)
    start = timezone.now()
    match.turn_started_at = start
    match.clock_blue_ms = 1000
    match.save()
    with patch(
        'thenewboston.dots_and_boxes.services.timezone.now',
        side_effect=[
            start + timedelta(milliseconds=999),
            start + timedelta(milliseconds=1001),
            *[start + timedelta(milliseconds=1002)] * 20,
        ],
    ):
        response = action(client, bucky, match, 'move', line=0)
    assert response.status_code == 200
    assert response.data['result_reason'] == 'timeout' and response.data['winner'] == 'red'
    assert response.data['lines'] == [0] * 40 and response.data['moves'] == []


def test_list_filters_by_participant_and_status(client, bucky, dmitry):
    active = accepted_match(client, bucky, dmitry)
    finished = accepted_match(client, bucky, dmitry)
    action(client, bucky, finished, 'resign')
    client.force_authenticate(bucky)
    assert [match['id'] for match in client.get(f'{BASE}?mine=1&status=pending,active').data['results']] == [active.id]
    assert [match['id'] for match in client.get(f'{BASE}?mine=1&status=finished').data['results']] == [finished.id]
    client.force_authenticate(baker.make('users.User'))
    assert client.get(f'{BASE}?mine=1').data['count'] == 0
    assert client.get(f'{BASE}?mine=exclude').data['count'] == 2


@pytest.mark.parametrize(
    'statuses,count',
    [
        ('active', 1),
        ('active,finished', 1),
        ('finished', 0),
        ('unknown', 0),
        ('\x00', 0),
        ('a\x00b,active', 1),
    ],
)
def test_status_filter_ignores_values_the_database_would_reject(client, bucky, statuses, count):
    match_id = create(client, bucky).data['id']
    response = client.get(BASE, {'status': statuses})
    assert response.status_code == 200
    assert [match['id'] for match in response.data['results']] == [match_id] * count


@pytest.mark.parametrize('model', [DotsAndBoxesEvent, DotsAndBoxesLedgerEntry, DotsAndBoxesMatch])
def test_game_records_are_view_only_in_admin(model):
    model_admin = admin.site._registry[model]
    assert not model_admin.has_add_permission(None)
    assert not model_admin.has_change_permission(None)
    assert not model_admin.has_delete_permission(None)


def test_staff_can_open_a_match_in_admin_but_not_save_it(client, bucky):
    match_id = create(client, bucky).data['id']
    staff = Client()
    staff.force_login(baker.make('users.User', is_staff=True, is_superuser=True))
    url = f'/admin/dots_and_boxes/dotsandboxesmatch/{match_id}/change/'
    assert staff.get(url).status_code == 200
    assert staff.get('/admin/dots_and_boxes/dotsandboxesmatch/').status_code == 200
    # Saving a form loaded before a move or a payout would write the old state back.
    assert staff.post(url, {}).status_code == 403
