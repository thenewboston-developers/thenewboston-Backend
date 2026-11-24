"""Checks shared by the staked board games: list filters and view-only admin pages."""

from contextlib import ExitStack
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib import admin
from django.test import Client
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.backgammon.models import BackgammonEvent, BackgammonLedgerEntry, BackgammonMatch
from thenewboston.battleship.models import BattleshipEvent, BattleshipLedgerEntry, BattleshipMatch
from thenewboston.checkers.models import CheckersEvent, CheckersLedgerEntry, CheckersMatch
from thenewboston.hex.models import HexEvent, HexLedgerEntry, HexMatch
from thenewboston.mancala.models import MancalaEvent, MancalaLedgerEntry, MancalaMatch
from thenewboston.reversi.models import ReversiEvent, ReversiLedgerEntry, ReversiMatch

pytestmark = pytest.mark.django_db
GAMES = ['backgammon', 'battleship', 'checkers', 'hex', 'mancala', 'reversi']
GAME_MODELS = [
    BackgammonEvent,
    BackgammonLedgerEntry,
    BackgammonMatch,
    BattleshipEvent,
    BattleshipLedgerEntry,
    BattleshipMatch,
    CheckersEvent,
    CheckersLedgerEntry,
    CheckersMatch,
    HexEvent,
    HexLedgerEntry,
    HexMatch,
    MancalaEvent,
    MancalaLedgerEntry,
    MancalaMatch,
    ReversiEvent,
    ReversiLedgerEntry,
    ReversiMatch,
]


@pytest.fixture(autouse=True)
def computer_queues():
    with ExitStack() as stack:
        for game in GAMES:
            stack.enter_context(patch(f'thenewboston.{game}.services.queue_computer'))
        yield


def create_computer_match(user, game):
    client = APIClient()
    client.force_authenticate(user)
    response = client.post(f'/api/{game}/matches', {'request_id': str(uuid4()), 'mode': 'computer'}, format='json')
    assert response.status_code == 201, response.data
    return client, response.data['id']


@pytest.mark.parametrize('game', GAMES)
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
def test_status_filter_ignores_values_the_database_would_reject(game, statuses, count, bucky):
    client, match_id = create_computer_match(bucky, game)
    response = client.get(f'/api/{game}/matches', {'status': statuses})
    assert response.status_code == 200
    assert [match['id'] for match in response.data['results']] == [match_id] * count


@pytest.mark.parametrize('model', GAME_MODELS, ids=lambda model: model.__name__)
def test_game_records_are_view_only_in_admin(model):
    model_admin = admin.site._registry[model]
    assert not model_admin.has_add_permission(None)
    assert not model_admin.has_change_permission(None)
    assert not model_admin.has_delete_permission(None)


@pytest.mark.parametrize('game', GAMES)
def test_staff_can_open_a_match_in_admin_but_not_save_it(game, bucky):
    _, match_id = create_computer_match(bucky, game)
    client = Client()
    client.force_login(baker.make('users.User', is_staff=True, is_superuser=True))
    url = f'/admin/{game}/{game}match/{match_id}/change/'
    response = client.get(url)
    assert response.status_code == 200
    # Saving a form loaded before a move or a payout would write the old state back.
    assert client.post(url, {}).status_code == 403


def test_battleship_admin_never_shows_a_hidden_fleet(bucky):
    _, match_id = create_computer_match(bucky, 'battleship')
    assert BattleshipMatch.objects.get(pk=match_id).fleet_guest
    client = Client()
    client.force_login(baker.make('users.User', is_staff=True, is_superuser=True))
    page = client.get(f'/admin/battleship/battleshipmatch/{match_id}/change/').content.decode().lower()
    assert 'status' in page
    for hidden in ('fleet', 'carrier', 'destroyer'):
        assert hidden not in page
