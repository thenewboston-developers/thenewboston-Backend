"""Signed-out visitors play free computer games through an expiring guest session."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.general.models import GuestGameSession
from thenewboston.general.tasks import delete_expired_guest_games
from thenewboston.reversi.models import ReversiMatch
from thenewboston.reversi.services import run_computer
from thenewboston.reversi.tests.test_rules import PASS_BOARD
from thenewboston.wallets.models import Wallet

BASE = '/api/reversi/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def computer_queue():
    cache.clear()
    with patch('thenewboston.reversi.services.queue_computer') as queue:
        yield queue


def guest_client():
    client = APIClient()
    response = client.post('/api/guest-games/session', {}, format='json')
    assert response.status_code == 201, response.data
    client.credentials(HTTP_X_GUEST_TOKEN=response.data['token'])
    return client


def create(client, **kwargs):
    payload = {'request_id': str(uuid4()), 'mode': 'computer', 'color': 'black', **kwargs}
    return client.post(BASE, payload, format='json')


def act(client, match, action, **kwargs):
    return client.post(f'{BASE}/{match.id}/{action}', {'expected_version': match.version, **kwargs}, format='json')


def test_guest_game_is_private_idempotent_and_never_creates_an_account():
    client = guest_client()
    before = get_user_model().objects.count(), Wallet.objects.count()
    request_id = str(uuid4())
    response = create(client, request_id=request_id)
    assert response.status_code == 201, response.data
    assert response['Cache-Control'] == 'private, no-store'
    assert response.data['guest_mode']
    assert (response.data['host_side'], response.data['your_side']) == ('black', 'black')
    assert response.data['black'] == {'id': 0, 'username': 'Guest', 'avatar': None}
    assert response.data['white'] is None
    assert create(client, request_id=request_id).data['id'] == response.data['id']
    assert create(client, request_id=request_id, difficulty='hard').status_code == 409
    assert before == (get_user_model().objects.count(), Wallet.objects.count())
    path = f'{BASE}/{response.data["id"]}'
    assert client.get(path).status_code == 200
    assert guest_client().get(path).status_code == 404
    assert APIClient().get(path).status_code == 404
    assert [match['id'] for match in client.get(BASE, {'mine': 'true'}).data['results']] == [response.data['id']]
    assert APIClient().get(BASE).data['count'] == 0
    assert guest_client().get(BASE).data['count'] == 0


def test_guest_keeps_its_color_and_sees_its_side(bucky):
    client = guest_client()
    response = create(client, color='white')
    assert (response.data['host_side'], response.data['your_side']) == ('white', 'white')
    assert response.data['white']['username'] == 'Guest'
    assert response.data['black'] is None
    match = ReversiMatch.objects.get(pk=response.data['id'])
    # The computer has black and moves first, so the guest must wait.
    assert act(client, match, 'move', row=2, column=3).status_code == 403
    run_computer(match.pk, match.version)
    match.refresh_from_db()
    assert match.active_side == 'white' and match.move_count == 1
    assert client.get(f'{BASE}/{match.id}').data['your_side'] == 'white'


def test_other_guests_and_members_cannot_see_or_change_a_guest_game(bucky):
    owner = guest_client()
    match = ReversiMatch.objects.get(pk=create(owner).data['id'])
    stranger = guest_client()
    assert act(stranger, match, 'resign').status_code == 404
    stranger.force_authenticate(bucky)
    assert stranger.get(f'{BASE}/{match.id}').status_code == 404
    assert act(stranger, match, 'move', row=2, column=3).status_code == 404
    assert act(owner, match, 'move', row=2, column=3).status_code == 200
    match.refresh_from_db()
    assert act(owner, match, 'resign').status_code == 200
    match.refresh_from_db()
    assert match.computer_reward == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}
    assert act(guest_client(), match, 'rematch').status_code == 404
    response = act(owner, match, 'rematch')
    assert response.status_code == 200, response.data
    assert response.data['id'] != match.id and response.data['guest_mode']
    assert response.data['host_side'] == 'black'
    assert ReversiMatch.objects.get(pk=response.data['id']).guest_session_id == match.guest_session_id


def test_guest_limits_expired_and_forged_tokens_and_stale_moves():
    client = guest_client()
    match = ReversiMatch.objects.get(pk=create(client).data['id'])
    assert act(client, match, 'resign', expected_version=999).status_code == 409
    GuestGameSession.objects.filter(pk=match.guest_session_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert client.get(f'{BASE}/{match.pk}').status_code == 401
    assert act(client, match, 'resign').status_code == 401
    client.credentials(HTTP_X_GUEST_TOKEN='forged')
    assert create(client).status_code == 401
    client = guest_client()
    for _ in range(10):
        assert create(client).status_code == 201
    assert create(client).status_code == 400


def test_guests_cannot_stake_challenge_or_answer_challenges(bucky, dmitry):
    client = guest_client()
    assert create(client, stake_amount=10).status_code == 400
    assert create(client, mode='human', opponent_id=bucky.id).status_code == 400
    assert not ReversiMatch.objects.exists()
    member = APIClient()
    member.force_authenticate(bucky)
    response = member.post(
        BASE, {'request_id': str(uuid4()), 'mode': 'human', 'opponent_id': dmitry.id, 'color': 'black'}, format='json'
    )
    challenge = ReversiMatch.objects.get(pk=response.data['id'])
    # A guest session only authorizes guest games: it is refused before the match is even looked up.
    for action in ('accept', 'decline', 'cancel'):
        assert act(client, challenge, action).status_code == 401
    challenge.refresh_from_db()
    assert challenge.status == 'pending'
    # Without any session a visitor can watch started games, never act.
    assert act(APIClient(), challenge, 'cancel').status_code == 401
    assert APIClient().post(BASE, {'request_id': str(uuid4()), 'mode': 'computer'}, format='json').status_code == 401


@pytest.mark.parametrize('funded', [True, False])
def test_guest_win_previews_the_reward_without_touching_the_fund(funded, tnb_currency):
    client = guest_client()
    balance = 100 if funded else 0
    fund, _ = GameFund.objects.update_or_create(
        pk=1, defaults={'balance': balance, 'total_deposited': balance, 'currency': tnb_currency}
    )
    wallets = Wallet.objects.count()
    match = ReversiMatch.objects.get(pk=create(client).data['id'])
    match.board = PASS_BOARD
    match.save()
    assert act(client, match, 'move', row=0, column=0).status_code == 200
    match.refresh_from_db()
    response = act(client, match, 'move', row=7, column=5)
    assert response.status_code == 200, response.data
    assert (response.data['status'], response.data['winner']) == ('finished', 'black')
    assert response.data['computer_reward'] == {
        'status': 'guest' if funded else 'fund_empty',
        'amount': 10 if funded else 0,
        'currency': 'TNB',
    }
    fund.refresh_from_db()
    assert fund.balance == balance and fund.total_paid == 0
    assert Wallet.objects.count() == wallets
    assert not GameRewardDecision.objects.exists()
    assert not ReversiMatch.objects.get(pk=match.pk).ledger_entries.exists()
    assert client.get(f'{BASE}/{match.pk}').data['computer_reward'] == response.data['computer_reward']


def test_guest_clock_is_settled_by_a_read_and_the_worker_cannot_replay_a_turn(computer_queue):
    client = guest_client()
    match = ReversiMatch.objects.get(pk=create(client).data['id'])
    assert act(client, match, 'move', row=2, column=3).status_code == 200
    match.refresh_from_db()
    computer_queue.assert_called_with(match)
    version = match.version
    run_computer(match.pk, version)
    run_computer(match.pk, version)
    match.refresh_from_db()
    assert (match.active_side, match.version, match.move_count) == ('black', version + 1, 2)
    match.clock_black_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    response = client.get(f'{BASE}/{match.pk}')
    assert (response.data['status'], response.data['winner'], response.data['result_reason']) == (
        'finished',
        'white',
        'timeout',
    )


def test_expired_guest_cleanup_removes_guest_games_only(bucky):
    expired = guest_client()
    live = guest_client()
    member = APIClient()
    member.force_authenticate(bucky)
    expired_match = ReversiMatch.objects.get(pk=create(expired).data['id'])
    assert act(expired, expired_match, 'move', row=2, column=3).status_code == 200
    live_match = ReversiMatch.objects.get(pk=create(live).data['id'])
    member_match = ReversiMatch.objects.get(pk=create(member).data['id'])
    GuestGameSession.objects.filter(pk=expired_match.guest_session_id).update(
        expires_at=timezone.now() - timedelta(days=1)
    )
    delete_expired_guest_games()
    assert not ReversiMatch.objects.filter(pk=expired_match.pk).exists()
    assert ReversiMatch.objects.filter(pk__in=[live_match.pk, member_match.pk]).count() == 2
    assert member_match.host == bucky and member_match.guest_session_id is None
