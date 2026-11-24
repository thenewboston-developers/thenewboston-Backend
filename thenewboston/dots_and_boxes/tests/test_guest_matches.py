"""Guest sessions may only play free computer matches, privately and without money."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.dots_and_boxes.models import DotsAndBoxesMatch
from thenewboston.dots_and_boxes.services import run_computer
from thenewboston.dots_and_boxes.tests.test_matches import one_line_left
from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.general.models import GuestGameSession
from thenewboston.general.tasks import delete_expired_guest_games
from thenewboston.wallets.models import Wallet

BASE = '/api/dots-and-boxes/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def computer_queue():
    cache.clear()
    with patch('thenewboston.dots_and_boxes.services.queue_computer') as queue:
        yield queue


def guest_client():
    client = APIClient()
    response = client.post('/api/guest-games/session', {}, format='json')
    assert response.status_code == 201, response.data
    client.credentials(HTTP_X_GUEST_TOKEN=response.data['token'])
    return client


def create(client, **kwargs):
    return client.post(BASE, {'request_id': str(uuid4()), 'mode': 'computer', **kwargs}, format='json')


def act(client, match, action, **kwargs):
    return client.post(f'{BASE}/{match.id}/{action}', {'expected_version': match.version, **kwargs}, format='json')


def test_guest_creation_is_private_idempotent_and_never_creates_account():
    client = guest_client()
    before = get_user_model().objects.count(), Wallet.objects.count()
    request_id = str(uuid4())
    response = create(client, request_id=request_id)
    assert response.status_code == 201, response.data
    assert response['Cache-Control'] == 'private, no-store'
    assert response.data['guest_mode'] and response.data['your_side'] == 'blue'
    assert response.data['blue'] == {'id': 0, 'username': 'Guest', 'avatar': None}
    assert create(client, request_id=request_id).data['id'] == response.data['id']
    assert create(client, request_id=request_id, difficulty='hard').status_code == 409
    assert create(client, request_id=request_id, board_size=3).status_code == 409
    assert before == (get_user_model().objects.count(), Wallet.objects.count())
    path = f'{BASE}/{response.data["id"]}'
    assert client.get(path).status_code == 200
    assert guest_client().get(path).status_code == 404
    assert APIClient().get(path).status_code == 404
    own = client.get(f'{BASE}?mine=true').data['results']
    assert [match['id'] for match in own] == [response.data['id']]
    assert APIClient().get(BASE).data['count'] == 0


def test_other_guest_cannot_mutate_rematch_or_hijack_with_account(bucky):
    owner = guest_client()
    match = DotsAndBoxesMatch.objects.get(pk=create(owner).data['id'])
    stranger = guest_client()
    assert act(stranger, match, 'move', line=0).status_code == 404
    assert act(stranger, match, 'resign').status_code == 404
    stranger.force_authenticate(bucky)
    assert act(stranger, match, 'resign').status_code == 404
    assert act(owner, match, 'resign').status_code == 200
    match.refresh_from_db()
    assert match.computer_reward == {'status': 'not_eligible', 'amount': 0, 'currency': 'TNB'}
    assert act(stranger, match, 'rematch').status_code == 404
    response = act(owner, match, 'rematch')
    assert response.status_code == 200, response.data
    assert response.data['id'] != match.id and response.data['guest_mode']
    assert DotsAndBoxesMatch.objects.get(pk=response.data['id']).guest_session_id == match.guest_session_id


def test_guest_limits_invalid_tokens_and_stale_moves():
    client = guest_client()
    match = DotsAndBoxesMatch.objects.get(pk=create(client).data['id'])
    assert act(client, match, 'move', line=0, expected_version=999).status_code == 409
    session = match.guest_session
    session.expires_at = timezone.now() - timedelta(seconds=1)
    session.save()
    assert client.get(f'{BASE}/{match.pk}').status_code == 401
    client.credentials(HTTP_X_GUEST_TOKEN='forged')
    assert create(client).status_code == 401
    client = guest_client()
    for _ in range(10):
        assert create(client).status_code == 201
    assert create(client).status_code == 400


def test_guests_cannot_stake_challenge_members_or_answer_challenges(bucky, dmitry):
    client = guest_client()
    assert create(client, stake_amount=10).status_code == 400
    assert create(client, mode='human', opponent_id=bucky.id).status_code == 400
    assert not DotsAndBoxesMatch.objects.exists()
    member = APIClient()
    member.force_authenticate(bucky)
    response = member.post(BASE, {'request_id': str(uuid4()), 'mode': 'human', 'opponent_id': dmitry.id}, format='json')
    challenge = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    # A guest token is not an account: answering a challenge is refused before the match is read.
    for name in ('accept', 'decline', 'cancel'):
        assert act(client, challenge, name).status_code == 401
    challenge.refresh_from_db()
    assert challenge.status == 'pending'


@pytest.mark.parametrize('funded', [True, False])
def test_guest_can_win_without_touching_fund_or_receiving_money(funded, tnb_currency):
    client = guest_client()
    balance = 100 if funded else 0
    fund, _ = GameFund.objects.update_or_create(
        pk=1, defaults={'balance': balance, 'total_deposited': balance, 'currency': tnb_currency}
    )
    wallets = Wallet.objects.count()
    match = DotsAndBoxesMatch.objects.get(pk=create(client, board_size=3).data['id'])
    last = one_line_left(match, blue=4, red=4)
    response = act(client, match, 'move', line=last)
    assert response.status_code == 200, response.data
    assert response.data['winner'] == 'blue'
    assert response.data['computer_reward'] == {
        'status': 'guest' if funded else 'fund_empty',
        'amount': 10 if funded else 0,
        'currency': 'TNB',
    }
    fund.refresh_from_db()
    assert fund.balance == balance and fund.total_paid == 0
    assert Wallet.objects.count() == wallets
    assert not GameRewardDecision.objects.exists()
    assert client.get(f'{BASE}/{match.pk}').data['computer_reward'] == response.data['computer_reward']


def test_guest_worker_plays_and_stale_worker_cannot_replay():
    client = guest_client()
    match = DotsAndBoxesMatch.objects.get(pk=create(client).data['id'])
    response = act(client, match, 'move', line=0)
    assert response.status_code == 200, response.data
    match.refresh_from_db()
    assert match.active_side == 'red'
    version = match.version
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.active_side == 'blue' and match.version == version + 1
    run_computer(match.id, version)
    match.refresh_from_db()
    assert match.version == version + 1
    assert not match.ledger_entries.exists()


def test_expired_guest_cleanup_deletes_guest_matches_and_keeps_member_matches(bucky):
    client = guest_client()
    guest_match = DotsAndBoxesMatch.objects.get(pk=create(client).data['id'])
    assert act(client, guest_match, 'move', line=0).status_code == 200
    member = APIClient()
    member.force_authenticate(bucky)
    member_match_id = create(member).data['id']
    GuestGameSession.objects.filter(pk=guest_match.guest_session_id).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    delete_expired_guest_games()
    assert list(DotsAndBoxesMatch.objects.values_list('pk', flat=True)) == [member_match_id]
