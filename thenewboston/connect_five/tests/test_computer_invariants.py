from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from rest_framework.test import APIClient

from thenewboston.connect_five.enums import MatchStatus
from thenewboston.connect_five.models import ConnectFiveMatch
from thenewboston.connect_five.services.computer import run_computer_turn
from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.wallets.models import Wallet

BASE = '/api/connect-five/matches'
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def no_queue_or_stream(monkeypatch):
    monkeypatch.setattr('thenewboston.connect_five.services.computer.queue_computer_turn', lambda match: None)
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)


def post(user, url, data):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(url, data, format='json')


def create(user, **kwargs):
    with patch('thenewboston.connect_five.services.computer.randbelow', return_value=0):
        response = post(user, f'{BASE}/computer', {'request_id': str(uuid4()), **kwargs})
    assert response.status_code == 201, response.data
    return ConnectFiveMatch.objects.get(pk=response.data['id'])


def concurrent(*actions):
    barrier = Barrier(len(actions))

    def run(action):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return action()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(actions)) as executor:
        futures = [executor.submit(run, action) for action in actions]
        return [future.result(timeout=20) for future in futures]


def test_duplicate_computer_create_does_not_create_two_games(bucky):
    request_id = str(uuid4())
    responses = concurrent(*[lambda: post(bucky, f'{BASE}/computer', {'request_id': request_id}) for _ in range(2)])
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].data['id'] == responses[1].data['id']
    assert ConnectFiveMatch.objects.count() == 1


def test_two_winning_move_requests_pay_only_once(bucky, bucky_tnb_wallet, tnb_currency):
    fund = GameFund.objects.create(currency=tnb_currency, balance=10, total_deposited=10)
    match = create(bucky)
    match.board_state[0][:4] = [1, 1, 1, 1]
    match.save()
    data = {'expected_version': match.version, 'move_type': 'SINGLE', 'x': 4, 'y': 0}
    responses = concurrent(*[lambda: post(bucky, f'{BASE}/{match.id}/move', data) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [200, 409]
    match.refresh_from_db()
    fund.refresh_from_db()
    bucky_tnb_wallet.refresh_from_db()
    assert match.status == MatchStatus.FINISHED_CONNECT5
    assert fund.balance == 0 and fund.total_paid == 10 and bucky_tnb_wallet.balance == 1010
    assert GameRewardDecision.objects.filter(game='connect_five', match_id=match.id).count() == 1
    assert match.events.filter(event_type='move').count() == 1


def test_duplicate_cpu_task_delivery_places_only_one_move(bucky):
    match = create(bucky)
    match.active_player = None
    match.save()
    with patch(
        'thenewboston.connect_five.services.computer.choose_move', return_value={'move_type': 'H2', 'x': 5, 'y': 5}
    ):
        concurrent(*[lambda: run_computer_turn(match.id, match.version) for _ in range(2)])
    match.refresh_from_db()
    assert match.version == 2
    assert match.players.get(user=None).inventory_h2 == 1
    assert match.events.filter(event_type='move').count() == 1


def test_concurrent_rematch_requests_create_one_active_rematch(bucky):
    match = create(bucky)
    response = post(bucky, f'{BASE}/{match.id}/resign', {'expected_version': match.version})
    assert response.status_code == 200
    responses = concurrent(
        *[
            lambda: post(bucky, f'{BASE}/computer', {'request_id': str(uuid4()), 'rematch_of': match.id})
            for _ in range(2)
        ]
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].data['id'] == responses[1].data['id']
    assert match.computer_rematches.count() == 1
