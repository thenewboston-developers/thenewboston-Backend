from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib import admin
from rest_framework.test import APIClient

from thenewboston.backgammon.models import BackgammonMatch
from thenewboston.backgammon.rules import initial_board, legal_turns
from thenewboston.backgammon.services import run_computer
from thenewboston.battleship.models import BattleshipMatch
from thenewboston.battleship.rules import resolve_shot, ship_cells
from thenewboston.game_rewards.admin import GameFundAdmin
from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.game_rewards.services import contribute, settle_computer_reward

pytestmark = pytest.mark.django_db


def winning_backgammon_board():
    board = initial_board()
    board['points'] = [0] * 24
    board['points'][0] = 1
    board['points'][6] = -14
    board['off'] = {'white': 14, 'black': 1}
    return board


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.parametrize('target,expected', [(1, 10), (3, 0)])
def test_backgammon_rewards_whole_match_only(bucky_tnb_wallet, dmitry_tnb_wallet, target, expected):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    client = client_for(bucky_tnb_wallet.owner)
    with patch('thenewboston.backgammon.services.queue_computer'):
        response = client.post(
            '/api/backgammon/matches', {'request_id': str(uuid4()), 'mode': 'computer', 'target_score': target}
        )
        assert response.status_code == 201
        match = BackgammonMatch.objects.get(pk=response.data['id'])
        match.board = winning_backgammon_board()
        match.dice = [1, 2]
        match.phase = 'moving'
        match.active_side = 'white'
        match.save()
        response = client.post(
            f'/api/backgammon/matches/{match.pk}/move',
            {'expected_version': match.version, 'moves': legal_turns(match.board, 'white', match.dice)[0]},
        )
    assert response.status_code == 200, response.data
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000 + expected
    assert GameRewardDecision.objects.count() == (1 if expected else 0)
    assert (response.data['computer_reward'] or {}).get('amount', 0) == expected


def test_backgammon_computer_declining_cube_can_win_completed_match_reward(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())
    with patch('thenewboston.backgammon.services.queue_computer'):
        response = client_for(bucky_tnb_wallet.owner).post(
            '/api/backgammon/matches', {'request_id': str(uuid4()), 'mode': 'computer'}
        )
    match = BackgammonMatch.objects.get(pk=response.data['id'])
    match.board = winning_backgammon_board()
    match.score_white = 2
    match.phase = 'doubling'
    match.double_offered_by = 'white'
    match.active_side = 'white'
    match.save()
    run_computer(match.pk, match.version)
    match.refresh_from_db()
    assert match.result_reason == 'double_declined'
    assert match.status == 'finished'
    assert match.computer_reward['amount'] == 10


def test_battleship_last_ship_pays_and_returns_receipt(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())
    client = client_for(bucky_tnb_wallet.owner)
    with patch('thenewboston.battleship.services.queue_computer'):
        response = client.post('/api/battleship/matches', {'request_id': str(uuid4()), 'mode': 'computer'})
        match = BattleshipMatch.objects.get(pk=response.data['id'])
        fleet = [
            {'id': name, 'row': row, 'column': 0, 'orientation': 'horizontal'}
            for row, name in enumerate(['carrier', 'battleship', 'cruiser', 'submarine', 'destroyer'])
        ]
        placed = client.post(
            f'/api/battleship/matches/{match.pk}/place', {'expected_version': match.version, 'ships': fleet}
        )
        assert placed.status_code == 200
        match.refresh_from_db()
        match.active_side = 'host'
        cells = [cell for ship in match.fleet_guest for cell in ship_cells(ship)]
        shots = []
        for row, column in cells[:-1]:
            shot, _ = resolve_shot(match.fleet_guest, shots, row, column)
            shots.append(shot)
        match.shots_host = shots
        match.save()
        row, column = cells[-1]
        response = client.post(
            f'/api/battleship/matches/{match.pk}/fire',
            {'expected_version': match.version, 'row': row, 'column': column},
        )
    assert response.status_code == 200, response.data
    assert response.data['computer_reward'] == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
    assert response.data['result_reason'] == 'fleet_sunk'
    assert client.get(f'/api/battleship/matches/{match.pk}').data['computer_reward']['amount'] == 10
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010
    assert GameFund.objects.get().balance == 0


@pytest.mark.parametrize('game', ['backgammon', 'battleship'])
def test_resigning_to_computer_never_awards_and_old_results_do_not_claim(game, bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())
    client = client_for(bucky_tnb_wallet.owner)
    with patch(f'thenewboston.{game}.services.queue_computer'):
        match = client.post(f'/api/{game}/matches', {'request_id': str(uuid4()), 'mode': 'computer'}).data
        result = client.post(f'/api/{game}/matches/{match["id"]}/resign', {'expected_version': match['version']})
    assert result.status_code == 200
    assert result.data['computer_reward']['status'] == 'not_eligible'
    assert GameFund.objects.get().balance == 10
    model = BackgammonMatch if game == 'backgammon' else BattleshipMatch
    model.objects.filter(pk=match['id']).update(computer_reward=None)
    GameRewardDecision.objects.all().delete()
    assert client.get(f'/api/{game}/matches/{match["id"]}').data['computer_reward'] is None
    assert GameRewardDecision.objects.count() == 0


def test_stale_admin_pause_does_not_overwrite_paid_reward(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=100, request_id=uuid4())
    stale = GameFund.objects.get()
    settle_computer_reward(game='battleship', match_id=1, user_id=dmitry_tnb_wallet.owner_id, won=True)
    stale.enabled = False
    GameFundAdmin(GameFund, admin.site).save_model(None, stale, None, True)
    fund = GameFund.objects.get()
    assert (fund.balance, fund.total_paid, fund.enabled) == (90, 10, False)
