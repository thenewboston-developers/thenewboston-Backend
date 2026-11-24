from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.backgammon.models import BackgammonMatch
from thenewboston.backgammon.rules import legal_turns
from thenewboston.backgammon.services import run_computer as run_backgammon
from thenewboston.backgammon.tests.test_matches import winning_board
from thenewboston.battleship.models import BattleshipMatch
from thenewboston.battleship.rules import ship_cells
from thenewboston.battleship.services import run_computer as run_battleship
from thenewboston.battleship.tests.test_rules import fleet
from thenewboston.connect_five.models import ConnectFiveMatch
from thenewboston.connect_five.services.computer import run_computer_turn
from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.general.models import GuestGameSession
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db
GAMES = ['battleship', 'backgammon', 'connect-five']
MODELS = dict(zip(GAMES, [BattleshipMatch, BackgammonMatch, ConnectFiveMatch]))


@pytest.fixture(autouse=True)
def queues():
    cache.clear()
    with (
        patch('thenewboston.battleship.services.queue_computer'),
        patch('thenewboston.backgammon.services.queue_computer'),
        patch('thenewboston.connect_five.services.computer.queue_computer_turn'),
        patch('thenewboston.connect_five.services.computer.randbelow', return_value=0),
    ):
        yield


def guest_client():
    client = APIClient()
    response = client.post('/api/guest-games/session', {}, format='json')
    assert response.status_code == 201, response.data
    assert response['Cache-Control'] == 'no-store'
    client.credentials(HTTP_X_GUEST_TOKEN=response.data['token'])
    return client


def create(client, game, **kwargs):
    path = f'/api/{game}/matches'
    payload = {'request_id': str(uuid4()), **kwargs}
    if game == 'connect-five':
        path += '/computer'
    else:
        payload.setdefault('mode', 'computer')
    return client.post(path, payload, format='json')


def act(client, game, match, action, **kwargs):
    return client.post(
        f'/api/{game}/matches/{match.id}/{action}', {'expected_version': match.version, **kwargs}, format='json'
    )


@pytest.mark.parametrize('game', GAMES)
def test_guest_creation_is_private_idempotent_and_never_creates_account(game):
    client = guest_client()
    before = get_user_model().objects.count(), Wallet.objects.count()
    request_id = str(uuid4())
    response = create(client, game, request_id=request_id)
    assert response.status_code == 201, response.data
    assert response.data['guest_mode']
    assert response.data['your_side'] == {'battleship': 'host', 'backgammon': 'white', 'connect-five': 'a'}[game]
    assert response.data[{'battleship': 'host', 'backgammon': 'white', 'connect-five': 'player_a'}[game]]['id'] == 0
    assert create(client, game, request_id=request_id).data['id'] == response.data['id']
    assert create(client, game, request_id=request_id, difficulty='hard').status_code == 409
    assert before == (get_user_model().objects.count(), Wallet.objects.count())
    path = f'/api/{game}/matches/{response.data["id"]}'
    assert client.get(path).status_code == 200
    assert guest_client().get(path).status_code == 404
    assert APIClient().get(path).status_code in {401, 404}
    own = client.get(f'/api/{game}/matches?mine=true').data['results']
    assert [match['id'] for match in own] == [response.data['id']]
    public = APIClient().get(f'/api/{game}/matches')
    if public.status_code == 200:
        assert response.data['id'] not in [match['id'] for match in public.data['results']]


@pytest.mark.parametrize('game', GAMES)
def test_other_guest_cannot_mutate_rematch_or_hijack_with_account(game, bucky):
    owner = guest_client()
    match = MODELS[game].objects.get(pk=create(owner, game).data['id'])
    stranger = guest_client()
    assert act(stranger, game, match, 'resign').status_code in {403, 404}
    stranger.force_authenticate(bucky)
    assert act(stranger, game, match, 'resign').status_code in {403, 404}
    assert act(owner, game, match, 'resign').status_code == 200
    match.refresh_from_db()
    assert match.computer_reward == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}
    assert act(stranger, game, match, 'rematch').status_code in {403, 404}
    response = act(owner, game, match, 'rematch')
    assert response.status_code in {200, 201}, response.data
    assert response.data['id'] != match.id and response.data['guest_mode']
    assert MODELS[game].objects.get(pk=response.data['id']).guest_session_id == match.guest_session_id


@pytest.mark.parametrize('game', GAMES)
def test_guest_limits_invalid_tokens_and_stale_moves(game):
    client = guest_client()
    response = create(client, game)
    match = MODELS[game].objects.get(pk=response.data['id'])
    assert act(client, game, match, 'resign', expected_version=999).status_code == 409
    session = match.guest_session
    session.expires_at = timezone.now() - timedelta(seconds=1)
    session.save()
    assert client.get(f'/api/{game}/matches/{match.pk}').status_code == 401
    client.credentials(HTTP_X_GUEST_TOKEN='forged')
    assert create(client, game).status_code == 401
    client = guest_client()
    for _ in range(10):
        assert create(client, game).status_code == 201
    assert create(client, game).status_code == 400


@pytest.mark.parametrize('game', GAMES)
def test_guests_cannot_stake_or_use_other_account_endpoints(game, bucky):
    client = guest_client()
    assert create(client, game, stake_amount=10).status_code == 400
    if game != 'connect-five':
        assert create(client, game, mode='human', opponent_id=bucky.id).status_code == 400
    assert client.post('/api/game-fund/contributions', {'amount': 10, 'request_id': str(uuid4())}).status_code in {
        401,
        404,
    }
    assert not MODELS[game].objects.exists()


@pytest.mark.parametrize('game', GAMES)
@pytest.mark.parametrize('funded', [True, False])
def test_guest_can_win_without_touching_fund_or_receiving_money(game, funded, tnb_currency):
    client = guest_client()
    balance = 100 if funded else 0
    fund, _ = GameFund.objects.update_or_create(
        pk=1, defaults={'balance': balance, 'total_deposited': balance, 'currency': tnb_currency}
    )
    wallets = Wallet.objects.count()
    response = create(client, game, **({'target_score': 1} if game == 'backgammon' else {}))
    match = MODELS[game].objects.get(pk=response.data['id'])
    if game == 'battleship':
        match.fleet_host = fleet()
        match.fleet_guest = fleet()
        cells = [cell for ship in fleet() for cell in ship_cells(ship)]
        row, column = cells.pop()
        match.shots_host = [{'row': r, 'column': c, 'result': 'hit'} for r, c in cells]
        match.phase = 'battle'
        match.active_side = 'host'
        match.turn_started_at = timezone.now()
        match.save()
        response = act(client, game, match, 'fire', row=row, column=column)
    elif game == 'backgammon':
        match.board = winning_board()
        match.active_side = 'white'
        match.phase = 'moving'
        match.dice = [1, 2]
        match.save()
        response = act(client, game, match, 'move', moves=legal_turns(match.board, 'white', match.dice)[0])
    else:
        match.board_state[0][:4] = [1, 1, 1, 1]
        match.save()
        response = act(client, game, match, 'move', move_type='SINGLE', x=4, y=0)
    assert response.status_code == 200, response.data
    assert response.data['computer_reward'] == {
        'status': 'guest' if funded else 'fund_empty',
        'amount': 10 if funded else 0,
        'currency': 'TNB',
    }
    fund.refresh_from_db()
    assert fund.balance == balance and fund.total_paid == 0
    assert Wallet.objects.count() == wallets
    assert not GameRewardDecision.objects.exists()
    match.refresh_from_db()
    assert client.get(f'/api/{game}/matches/{match.pk}').data['computer_reward'] == response.data['computer_reward']


def test_guest_connect_five_worker_has_distinct_inventory_and_turn():
    client = guest_client()
    match = ConnectFiveMatch.objects.get(pk=create(client, 'connect-five').data['id'])
    assert match.players.filter(is_guest=True).count() == 1
    assert match.players.filter(user=None, is_guest=False).count() == 1
    response = act(client, 'connect-five', match, 'move', move_type='H2', x=4, y=4)
    assert response.status_code == 200, response.data
    assert response.data['active_side'] == 'b'
    match.refresh_from_db()
    assert match.players.get(is_guest=True).inventory_h2 == 1
    assert match.players.get(is_guest=False).inventory_h2 == 2
    run_computer_turn(match.id, match.version)
    match.refresh_from_db()
    assert match.guest_active_side == 'a' and match.turn_number == 3
    assert client.get(f'/api/connect-five/matches/{match.pk}').data['active_side'] == 'a'


@pytest.mark.parametrize('game', ['backgammon', 'battleship'])
def test_guest_existing_worker_plays_computer(game):
    client = guest_client()
    match = MODELS[game].objects.get(pk=create(client, game).data['id'])
    if game == 'battleship':
        match.fleet_host = fleet()
        match.phase = 'battle'
        match.active_side = 'guest'
        match.turn_started_at = timezone.now()
        match.save()
        run_battleship(match.id, match.version)
        match.refresh_from_db()
        assert len(match.shots_guest) == 1 and match.active_side == 'host'
        assert 'fleet_guest' not in client.get(f'/api/{game}/matches/{match.pk}').data
    else:
        match.active_side = 'black'
        match.save()
        run_backgammon(match.id, match.version)
        match.refresh_from_db()
        assert match.active_side == 'white'
        assert match.events.filter(event_type='move').exists()


def test_session_endpoint_is_throttled():
    for _ in range(20):
        assert APIClient().post('/api/guest-games/session', {}).status_code == 201
    assert APIClient().post('/api/guest-games/session', {}).status_code == 429
    assert GuestGameSession.objects.count() == 20


def test_expired_guest_cleanup_preserves_accounts_and_live_sessions(bucky):
    from thenewboston.general.tasks import delete_expired_guest_games

    expired_client = guest_client()
    live_client = guest_client()
    matches = [MODELS[game].objects.get(pk=create(expired_client, game).data['id']) for game in GAMES]
    live_match = BattleshipMatch.objects.get(pk=create(live_client, 'battleship').data['id'])
    GuestGameSession.objects.filter(pk=matches[0].guest_session_id).update(
        expires_at=timezone.now() - timedelta(days=1)
    )
    before = get_user_model().objects.count()
    delete_expired_guest_games()
    assert get_user_model().objects.count() == before
    assert GuestGameSession.objects.count() == 1
    for match in matches:
        assert not type(match).objects.filter(pk=match.pk).exists()
    assert BattleshipMatch.objects.filter(pk=live_match.pk).exists()


def test_guest_session_response_not_written_to_debug_log(caplog, settings):
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, 'thenewboston.general.middleware.LoggingMiddleware']
    with caplog.at_level('DEBUG', logger='thenewboston.general.middleware'):
        response = APIClient().post('/api/guest-games/session', {})
    assert response.status_code == 201
    assert response.data['token'] not in caplog.text
    assert '(guest session hidden)' in caplog.text


def test_guest_reward_requires_enabled_and_configured_fund(tnb_currency):
    from thenewboston.game_rewards.services import settle_computer_reward

    fund, _ = GameFund.objects.update_or_create(pk=1, defaults={'balance': 100, 'total_deposited': 100})
    receipt = settle_computer_reward(game='battleship', match_id=1, user_id=None, won=True)
    assert receipt == {'status': 'fund_empty', 'amount': 0, 'currency': 'TNB'}
    fund.currency = tnb_currency
    fund.enabled = False
    fund.save()
    assert settle_computer_reward(game='battleship', match_id=1, user_id=None, won=True) == receipt
    assert not GameRewardDecision.objects.exists()
