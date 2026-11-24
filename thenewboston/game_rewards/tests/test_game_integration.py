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
from thenewboston.mancala.models import MancalaMatch
from thenewboston.mancala.services import run_computer as run_mancala_computer

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


def mancala_match(client, board, active_side='host'):
    with patch('thenewboston.mancala.services.queue_computer'):
        response = client.post('/api/mancala/matches', {'request_id': str(uuid4()), 'mode': 'computer'})
    assert response.status_code == 201, response.data
    match = MancalaMatch.objects.get(pk=response.data['id'])
    match.board = board
    match.active_side = active_side
    match.save()
    return match


def test_mancala_win_on_stones_pays_and_returns_receipt(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())
    client = client_for(bucky_tnb_wallet.owner)
    # The player's last stone ends the game 27 to 21.
    match = mancala_match(client, [0, 0, 0, 0, 0, 1, 26, 1, 2, 3, 0, 0, 0, 15])
    with patch('thenewboston.mancala.services.queue_computer'):
        response = client.post(f'/api/mancala/matches/{match.pk}/move', {'expected_version': match.version, 'pit': 5})
    assert response.status_code == 200, response.data
    assert response.data['computer_reward'] == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
    assert (response.data['winner'], response.data['result_reason']) == ('host', 'stones')
    assert client.get(f'/api/mancala/matches/{match.pk}').data['computer_reward']['amount'] == 10
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010
    assert GameFund.objects.get().balance == 0
    assert GameRewardDecision.objects.get().game == 'mancala'


def test_mancala_win_decided_by_the_computers_last_move_still_pays(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())
    # The computer's only move empties its row, and the player keeps the stones left on their side.
    match = mancala_match(
        client_for(bucky_tnb_wallet.owner), [1, 2, 3, 0, 0, 0, 20, 0, 0, 0, 0, 0, 1, 21], active_side='guest'
    )
    with patch('thenewboston.mancala.services.queue_computer'):
        run_mancala_computer(match.pk, match.version)
    match.refresh_from_db()
    assert (match.status, match.winner, match.result_reason) == ('finished', 'host', 'stones')
    assert match.board == [0, 0, 0, 0, 0, 0, 26, 0, 0, 0, 0, 0, 0, 22]
    assert match.computer_reward == {'status': 'paid', 'amount': 10, 'currency': 'TNB'}
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010


@pytest.mark.parametrize(
    'board,status',
    [
        # 24 all: a draw is not a win.
        ([0, 0, 0, 0, 0, 1, 23, 1, 2, 0, 0, 0, 0, 21], 'not_eligible'),
        # The computer finishes ahead 21 to 27.
        ([0, 0, 0, 0, 0, 1, 20, 1, 2, 3, 0, 0, 0, 21], 'not_eligible'),
    ],
)
def test_mancala_draw_or_loss_to_computer_earns_nothing(bucky_tnb_wallet, dmitry_tnb_wallet, board, status):
    contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())
    client = client_for(bucky_tnb_wallet.owner)
    match = mancala_match(client, board)
    with patch('thenewboston.mancala.services.queue_computer'):
        response = client.post(f'/api/mancala/matches/{match.pk}/move', {'expected_version': match.version, 'pit': 5})
    assert response.status_code == 200, response.data
    assert response.data['status'] == 'finished'
    assert response.data['computer_reward'] == {'status': status, 'amount': 0, 'currency': 'TNB'}
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert GameFund.objects.get().balance == 10


def test_mancala_win_with_an_empty_fund_is_recorded_and_never_paid_later(bucky_tnb_wallet, dmitry_tnb_wallet):
    client = client_for(bucky_tnb_wallet.owner)
    match = mancala_match(client, [0, 0, 0, 0, 0, 1, 26, 1, 2, 3, 0, 0, 0, 15])
    with patch('thenewboston.mancala.services.queue_computer'):
        response = client.post(f'/api/mancala/matches/{match.pk}/move', {'expected_version': match.version, 'pit': 5})
    assert response.data['computer_reward'] == {'status': 'fund_empty', 'amount': 0, 'currency': 'TNB'}
    contribute(user=dmitry_tnb_wallet.owner, amount=100, request_id=uuid4())
    assert client.get(f'/api/mancala/matches/{match.pk}').data['computer_reward']['status'] == 'fund_empty'
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1000
    assert GameFund.objects.get().balance == 100


@pytest.mark.parametrize('game', ['backgammon', 'battleship', 'mancala'])
def test_resigning_to_computer_never_awards_and_old_results_do_not_claim(game, bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())
    client = client_for(bucky_tnb_wallet.owner)
    with patch(f'thenewboston.{game}.services.queue_computer'):
        match = client.post(f'/api/{game}/matches', {'request_id': str(uuid4()), 'mode': 'computer'}).data
        result = client.post(f'/api/{game}/matches/{match["id"]}/resign', {'expected_version': match['version']})
    assert result.status_code == 200
    assert result.data['computer_reward']['status'] == 'not_eligible'
    assert GameFund.objects.get().balance == 10
    model = {'backgammon': BackgammonMatch, 'battleship': BattleshipMatch, 'mancala': MancalaMatch}[game]
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
