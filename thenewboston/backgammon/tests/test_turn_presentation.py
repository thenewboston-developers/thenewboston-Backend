from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import transaction
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from thenewboston.backgammon.models import BackgammonEvent, BackgammonMatch
from thenewboston.backgammon.rules import apply_turn, initial_board, legal_turns
from thenewboston.backgammon.serializers import MatchReadSerializer
from thenewboston.backgammon.services import run_computer, start_next_game
from thenewboston.backgammon.views import BackgammonMatchViewSet

BASE = '/api/backgammon/matches'
pytestmark = pytest.mark.django_db


@pytest.fixture
def client(bucky):
    client = APIClient()
    client.force_authenticate(bucky)
    return client


@pytest.fixture(autouse=True)
def computer_queue():
    with patch('thenewboston.backgammon.services.queue_computer'):
        yield


def create_match(client, opening=(1, 6)):
    with patch('thenewboston.backgammon.services.roll_dice', return_value=list(opening)):
        response = client.post(BASE, {'request_id': str(uuid4()), 'mode': 'computer'})
    assert response.status_code == 201
    assert response.data['last_turn'] is None
    return BackgammonMatch.objects.get(pk=response.data['id'])


@pytest.mark.parametrize('phase', ['moving', 'awaiting_roll'])
def test_completed_computer_turn_exposes_actual_dice_and_moves(client, phase):
    match = create_match(client)
    if phase == 'awaiting_roll':
        match.phase = phase
        match.dice = []
        match.save()
    dice = [1, 6] if phase == 'moving' else [4, 4]
    version = match.version
    with patch('thenewboston.backgammon.services.roll_dice', return_value=dice):
        run_computer(match.id, version)
    response = client.get(f'{BASE}/{match.id}')
    assert response.status_code == 200
    assert response.data['phase'] == 'awaiting_roll'
    assert response.data['dice'] == []
    last_turn = response.data['last_turn']
    assert last_turn['version'] == version + 1
    assert last_turn['side'] == 'black'
    assert last_turn['dice'] == dice
    assert apply_turn(initial_board(), 'black', dice, last_turn['moves']) == response.data['board']


def test_move_response_includes_completed_human_turn(client):
    match = create_match(client, opening=(6, 1))
    moves = legal_turns(match.board, 'white', match.dice)[0]
    response = client.post(
        f'{BASE}/{match.id}/move',
        {'expected_version': match.version, 'moves': moves},
        format='json',
    )
    assert response.status_code == 200
    assert response.data['last_turn'] == {
        'version': match.version + 1,
        'side': 'white',
        'dice': [6, 1],
        'moves': moves,
    }


def test_completed_turn_identity_survives_polling_and_next_roll(client):
    match = create_match(client)
    run_computer(match.id, match.version)
    first = client.get(f'{BASE}/{match.id}').data
    assert client.get(f'{BASE}/{match.id}').data['last_turn'] == first['last_turn']
    response = client.post(f'{BASE}/{match.id}/roll', {'expected_version': first['version']})
    assert response.status_code == 200
    assert response.data['version'] > first['last_turn']['version']
    assert response.data['last_turn'] == first['last_turn']


def test_new_game_does_not_replay_previous_completed_turn(client):
    match = create_match(client)
    run_computer(match.id, match.version)
    match.refresh_from_db()
    assert client.get(f'{BASE}/{match.id}').data['last_turn']
    match.status = 'between_games'
    match.save()
    with transaction.atomic():
        start_next_game(match)
    response = client.get(f'{BASE}/{match.id}')
    assert response.data['game_number'] == 2
    assert response.data['last_turn'] is None


def test_completed_turn_query_cannot_get_ahead_of_match_snapshot(client, django_assert_num_queries):
    match = create_match(client)
    run_computer(match.id, match.version)
    match.refresh_from_db()
    expected = client.get(f'{BASE}/{match.id}').data['last_turn']
    BackgammonEvent.objects.create(
        match=match,
        version=match.version + 1,
        event_type='move',
        payload={'side': 'white', 'dice': [6, 6], 'moves': []},
    )
    with django_assert_num_queries(1):
        assert MatchReadSerializer(context={'detail': True}).get_last_turn(match) == expected


@pytest.mark.parametrize('count', [1, 5])
def test_lobby_omits_turns_without_per_match_queries(client, bucky, count, django_assert_num_queries):
    for _ in range(count):
        match = create_match(client)
        run_computer(match.id, match.version)
    request = APIRequestFactory().get(BASE)
    force_authenticate(request, user=bucky)
    with django_assert_num_queries(2):
        response = BackgammonMatchViewSet.as_view({'get': 'list'})(request)
    assert response.status_code == 200
    assert response.data['count'] == count
    assert all('last_turn' not in match for match in response.data['results'])
