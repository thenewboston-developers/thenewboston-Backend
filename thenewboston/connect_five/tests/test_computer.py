from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.connect_five.constants import create_empty_board
from thenewboston.connect_five.enums import MatchStatus
from thenewboston.connect_five.models import (
    ConnectFiveChallenge,
    ConnectFiveEscrow,
    ConnectFiveLedgerEntry,
    ConnectFiveMatch,
    ConnectFiveStats,
)
from thenewboston.connect_five.services.computer import (
    finish_computer_match,
    queue_computer_turn as enqueue_computer_turn,
    run_computer_turn,
)
from thenewboston.connect_five.services.streaming import stream_match_update
from thenewboston.connect_five.tasks import sweep_connect_five_timeouts_task
from thenewboston.game_rewards.models import GameFund, GameRewardDecision

BASE = '/api/connect-five/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.connect_five.services.computer.queue_computer_turn') as queue:
        yield queue


def create(client, user, **kwargs):
    client.force_authenticate(user)
    with patch('thenewboston.connect_five.services.computer.randbelow', return_value=0):
        return client.post(f'{BASE}/computer', {'request_id': str(uuid4()), **kwargs}, format='json')


def new_match(client, user, **kwargs):
    response = create(client, user, **kwargs)
    assert response.status_code == 201, response.data
    return ConnectFiveMatch.objects.get(pk=response.data['id'])


def act(client, user, match, action='move', **kwargs):
    client.force_authenticate(user)
    return client.post(f'{BASE}/{match.id}/{action}', {'expected_version': match.version, **kwargs}, format='json')


def winning_match(client, user):
    match = new_match(client, user)
    match.board_state[0][:4] = [1, 1, 1, 1]
    match.save()
    return match


def test_computer_creation_is_free_without_currency_wallet_or_fake_user(client, bucky):
    user_count = get_user_model().objects.count()
    response = create(client, bucky)
    assert response.status_code == 201
    match = response.data
    assert match['mode'] == 'computer' and match['difficulty'] == 'normal'
    assert match['player_a']['id'] == bucky.id
    assert match['player_b'] is None and match['challenge'] is None
    assert match['active_side'] == 'a' and match['winner_side'] is None
    assert match['computer_name'] == 'Computer' and match['version'] == 1
    assert match['computer_reward'] is None
    assert match['max_spend_amount'] == match['prize_pool_total'] == 0
    assert match['server_time']
    assert len(match['players']) == 2
    for player in match['players']:
        assert (player['inventory_h2'], player['inventory_v2'], player['inventory_bomb']) == (2, 2, 2)
        assert player['spent_total'] == 0
    assert get_user_model().objects.count() == user_count
    assert not ConnectFiveChallenge.objects.exists()
    assert not ConnectFiveEscrow.objects.exists()
    assert not ConnectFiveLedgerEntry.objects.exists()
    assert not ConnectFiveStats.objects.exists()


@pytest.mark.parametrize(
    'settings',
    [
        {'stake_amount': 0},
        {'stake_amount': 10},
        {'max_spend_amount': 1},
        {'opponent_id': 123},
        {'difficulty': 'expert'},
        {'time_limit_seconds': 1},
        {'request_id': 'bad'},
        {'rematch_of': -1},
    ],
)
def test_invalid_computer_settings_rejected(client, bucky, settings):
    assert create(client, bucky, **settings).status_code == 400
    assert not ConnectFiveMatch.objects.exists()


def test_create_retry_idempotency_and_mismatched_reuse(client, bucky):
    request_id = str(uuid4())
    first = create(client, bucky, request_id=request_id)
    second = create(client, bucky, request_id=request_id)
    assert first.status_code == second.status_code == 201
    assert first.data['id'] == second.data['id']
    assert create(client, bucky, request_id=request_id, difficulty='hard').status_code == 409
    assert ConnectFiveMatch.objects.count() == 1


def test_authentication_and_owner_only_visibility(client, bucky, dmitry):
    assert client.post(f'{BASE}/computer', {'request_id': str(uuid4())}, format='json').status_code == 401
    match = new_match(client, bucky)
    client.force_authenticate(dmitry)
    assert client.get(BASE).data['count'] == 0
    assert client.get(f'{BASE}/{match.id}').status_code == 404
    assert act(client, dmitry, match, move_type='SINGLE', x=0, y=0).status_code == 403
    assert act(client, dmitry, match, 'resign').status_code == 403
    client.force_authenticate(None)
    assert client.get(BASE).data['count'] == 0
    assert client.get(f'{BASE}/{match.id}').status_code == 404


def test_free_special_move_is_authoritative_and_cannot_be_purchased(client, bucky):
    match = new_match(client, bucky)
    response = act(client, bucky, match, move_type='H2', x=5, y=5)
    assert response.status_code == 200
    assert response.data['board_state'][5][5:7] == [1, 1]
    assert response.data['active_side'] == 'b' and response.data['active_player'] is None
    assert response.data['version'] == 2
    player = match.players.get(user=bucky)
    assert player.inventory_h2 == 1
    assert act(client, bucky, match, 'purchase', special_type='H2', quantity=1).status_code == 400
    assert not ConnectFiveLedgerEntry.objects.exists()


@pytest.mark.parametrize(
    'move',
    [
        {'move_type': 'SINGLE', 'x': -1, 'y': 0},
        {'move_type': 'SINGLE', 'x': 15, 'y': 0},
        {'move_type': 'H2', 'x': 14, 'y': 0},
        {'move_type': 'V2', 'x': 0, 'y': 14},
        {'move_type': 'BOMB', 'x': 0, 'y': 0},
        {'move_type': 'NO', 'x': 0, 'y': 0},
        {'move_type': 'SINGLE', 'x': [], 'y': 0},
    ],
)
def test_invalid_moves_do_not_change_board_inventory_clock_or_version(client, bucky, move):
    match = new_match(client, bucky)
    before = (match.board_state, match.clock_a_remaining_ms, match.version)
    assert act(client, bucky, match, **move).status_code == 400
    match.refresh_from_db()
    assert (match.board_state, match.clock_a_remaining_ms, match.version) == before
    assert match.players.get(user=bucky).inventory_h2 == 2


def test_exhausted_special_is_rejected_and_bomb_only_removes_enemy(client, bucky):
    match = new_match(client, bucky)
    player = match.players.get(user=bucky)
    player.inventory_h2 = 0
    player.save()
    assert act(client, bucky, match, move_type='H2', x=0, y=0).status_code == 400
    match.board_state[3][3] = 2
    match.board_state[4][4] = 1
    match.save()
    assert act(client, bucky, match, move_type='BOMB', x=4, y=4).status_code == 400
    response = act(client, bucky, match, move_type='BOMB', x=3, y=3)
    assert response.status_code == 200
    assert response.data['board_state'][3][3] == 0
    assert response.data['board_state'][4][4] == 1
    assert match.players.get(user=bucky).inventory_bomb == 1


def test_stale_moves_cannot_play_again_after_cpu_turn(client, bucky):
    match = new_match(client, bucky)
    assert act(client, bucky, match, move_type='SINGLE', x=0, y=0).status_code == 200
    stale_version = match.version
    match.refresh_from_db()
    with patch(
        'thenewboston.connect_five.services.computer.choose_move', return_value={'move_type': 'SINGLE', 'x': 1, 'y': 0}
    ):
        run_computer_turn(match.id, match.version)
    match.refresh_from_db()
    assert match.active_player_id == bucky.id
    response = act(client, bucky, match, expected_version=stale_version, move_type='SINGLE', x=2, y=0)
    assert response.status_code == 409
    assert len(list(match.events.filter(event_type='move'))) == 2
    assert (
        client.post(f'{BASE}/{match.id}/move', {'move_type': 'SINGLE', 'x': 2, 'y': 0}, format='json').status_code
        == 400
    )


def test_computer_win_pays_ten_once_without_ranked_stats(client, bucky, bucky_tnb_wallet, tnb_currency):
    stats = ConnectFiveStats.objects.create(user=bucky, elo=1765, matches_played=7, wins=4, losses=3)
    fund = GameFund.objects.create(currency=tnb_currency, balance=20, total_deposited=20)
    match = winning_match(client, bucky)
    response = act(client, bucky, match, move_type='SINGLE', x=4, y=0)
    assert response.status_code == 200
    assert response.data['status'] == MatchStatus.FINISHED_CONNECT5
    assert response.data['winner_side'] == 'a' and response.data['winner'] == bucky.id
    assert response.data['computer_reward'] == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
    assert response.data['player_a_elo_after'] is None
    bucky_tnb_wallet.refresh_from_db()
    fund.refresh_from_db()
    stats.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010 and fund.balance == 10 and fund.total_paid == 10
    assert (stats.elo, stats.matches_played, stats.wins, stats.losses) == (1765, 7, 4, 3)
    assert not ConnectFiveEscrow.objects.exists() and not ConnectFiveLedgerEntry.objects.exists()
    assert act(client, bucky, match, move_type='SINGLE', x=4, y=0).status_code == 409
    match.refresh_from_db()
    with transaction.atomic():
        finish_computer_match(match=match, winner_side='a', status=MatchStatus.FINISHED_CONNECT5)
    assert GameRewardDecision.objects.filter(game='connect_five', match_id=match.id).count() == 1


def test_empty_fund_win_is_final_and_not_paid_after_later_topup(client, bucky, bucky_tnb_wallet, tnb_currency):
    match = winning_match(client, bucky)
    response = act(client, bucky, match, move_type='SINGLE', x=4, y=0)
    assert response.data['computer_reward']['status'] == 'fund_empty'
    fund = GameFund.objects.get(pk=1)
    fund.currency = tnb_currency
    fund.balance = fund.total_deposited = 100
    fund.save()
    assert client.get(f'{BASE}/{match.id}').data['computer_reward']['status'] == 'fund_empty'
    sweep_connect_five_timeouts_task()
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000


@pytest.mark.parametrize('result', ['resign', 'player_timeout', 'cpu_timeout', 'cpu_win', 'full_board'])
def test_non_board_human_wins_and_losses_do_not_receive_rewards(client, bucky, bucky_tnb_wallet, tnb_currency, result):
    fund = GameFund.objects.create(currency=tnb_currency, balance=20, total_deposited=20)
    match = new_match(client, bucky)
    if result == 'resign':
        response = act(client, bucky, match, 'resign')
    elif result in {'player_timeout', 'cpu_timeout'}:
        match.active_player = bucky if result == 'player_timeout' else None
        match.clock_a_remaining_ms = match.clock_b_remaining_ms = 1
        match.turn_started_at = timezone.now() - timedelta(seconds=1)
        match.save()
        response = client.get(f'{BASE}/{match.id}')
        assert response.data['winner_side'] == ('b' if result == 'player_timeout' else 'a')
        assert response.data['status'] == MatchStatus.FINISHED_TIMEOUT
    elif result == 'cpu_win':
        match.active_player = None
        match.board_state[0][:4] = [2, 2, 2, 2]
        match.save()
        with patch(
            'thenewboston.connect_five.services.computer.choose_move',
            return_value={'move_type': 'SINGLE', 'x': 4, 'y': 0},
        ):
            run_computer_turn(match.id, match.version)
        response = client.get(f'{BASE}/{match.id}')
        assert response.data['winner_side'] == 'b' and response.data['winner'] is None
    else:
        match.board_state = [[1 if (x + 2 * y) % 4 < 2 else 2 for x in range(15)] for y in range(15)]
        match.board_state[14][14] = 0
        match.turn_number = 225
        match.save()
        response = act(client, bucky, match, move_type='SINGLE', x=14, y=14)
        assert response.data['status'] == MatchStatus.FINISHED_FULL_BOARD
    assert response.status_code == 200, response.data
    assert response.data['computer_reward'] == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}
    bucky_tnb_wallet.refresh_from_db()
    fund.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 and fund.balance == 20


def test_cpu_task_is_legal_and_duplicate_delivery_is_noop(client, bucky):
    match = new_match(client, bucky)
    match.active_player = None
    match.save()
    version = match.version
    with patch(
        'thenewboston.connect_five.services.computer.choose_move', return_value={'move_type': 'V2', 'x': 7, 'y': 7}
    ):
        run_computer_turn(match.id, version)
        run_computer_turn(match.id, version)
    match.refresh_from_db()
    assert match.version == version + 1
    assert match.board_state[7][7] == match.board_state[8][7] == 2
    assert match.active_player_id == bucky.id
    assert match.players.get(user=None).inventory_v2 == 1
    event = match.events.get(event_type='move')
    assert event.actor_id is None and event.payload['side'] == 'b'


def test_queue_failure_is_recovered_by_existing_sweep(client, bucky):
    match = new_match(client, bucky)
    match.active_player = None
    match.save()
    with patch(
        'thenewboston.connect_five.tasks.play_connect_five_computer_turn.delay', side_effect=[ConnectionError, None]
    ) as delay:
        enqueue_computer_turn(match)
        sweep_connect_five_timeouts_task()
    assert delay.call_count == 2
    assert all(call.args == (match.id, match.version) for call in delay.call_args_list)


def test_cpu_results_do_not_broadcast_to_public_or_user_websockets(client, bucky):
    match = new_match(client, bucky)
    with patch('thenewboston.connect_five.services.streaming.ConnectFiveConsumer.stream_match') as private:
        with patch('thenewboston.connect_five.services.streaming.ConnectFivePublicConsumer.stream_match') as public:
            stream_match_update(match=match)
    private.assert_not_called()
    public.assert_not_called()


def test_rematch_creates_free_match_same_terms_and_deduplicates_active_retries(client, bucky, dmitry):
    match = new_match(client, bucky, difficulty='hard', time_limit_seconds=300)
    assert create(client, bucky, rematch_of=match.id, difficulty='hard', time_limit_seconds=300).status_code == 409
    act(client, bucky, match, 'resign')
    first = create(client, bucky, rematch_of=match.id, difficulty='hard', time_limit_seconds=300)
    second = create(client, bucky, rematch_of=match.id, difficulty='hard', time_limit_seconds=300)
    assert first.status_code == second.status_code == 201
    assert first.data['id'] == second.data['id'] != match.id
    assert first.data['board_state'] == create_empty_board()
    assert first.data['computer_reward'] is None
    assert create(client, dmitry, rematch_of=match.id, difficulty='hard', time_limit_seconds=300).status_code == 404
    assert create(client, bucky, rematch_of=match.id, difficulty='easy', time_limit_seconds=300).status_code == 400


def test_human_stakes_moves_purchases_and_rankings_remain_supported(
    client, bucky, dmitry, bucky_tnb_wallet, dmitry_tnb_wallet
):
    client.force_authenticate(bucky)
    response = client.post(
        '/api/connect-five/challenges',
        {
            'opponent_id': dmitry.id,
            'stake_amount': 10,
            'max_spend_amount': 20,
            'time_limit_seconds': 300,
        },
        format='json',
    )
    assert response.status_code == 201
    client.force_authenticate(dmitry)
    response = client.post(f'/api/connect-five/challenges/{response.data["id"]}/accept', {}, format='json')
    assert response.status_code == 200, response.data
    match = ConnectFiveMatch.objects.get(pk=response.data['id'])
    assert response.data['mode'] == 'human' and response.data['player_b'] is not None
    assert response.data['computer_reward'] is None
    response = client.post(f'{BASE}/{match.id}/purchase', {'special_type': 'H2', 'quantity': 1}, format='json')
    assert response.status_code == 200, response.data
    assert response.data['prize_pool_total'] == 24
    response = client.post(f'{BASE}/{match.id}/move', {'move_type': 'H2', 'x': 0, 'y': 0}, format='json')
    assert response.status_code == 200, response.data
    client.force_authenticate(bucky)
    response = client.post(f'{BASE}/{match.id}/resign', {}, format='json')
    assert response.status_code == 200
    assert response.data['winner'] == dmitry.id
    assert response.data['player_b_elo_after'] is not None
    assert not GameRewardDecision.objects.exists()
    assert ConnectFiveStats.objects.get(user=dmitry).wins == 1


@pytest.mark.parametrize('action', ['move', 'purchase', 'resign', 'rematch'])
def test_unknown_match_actions_return_not_found(client, bucky, action):
    client.force_authenticate(bucky)
    assert client.post(f'{BASE}/999999/{action}', {'expected_version': 1}, format='json').status_code == 404
