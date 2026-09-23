import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from thenewboston.connect_five.models import (
    ConnectFiveChallenge,
    ConnectFiveChatMessage,
    ConnectFiveMatch,
    ConnectFiveMatchPlayer,
    ConnectFiveStats,
)
from thenewboston.connect_five.views.challenge import ConnectFiveChallengeViewSet
from thenewboston.connect_five.views.match import ConnectFiveMatchViewSet


def create_challenge(challenger, opponent, currency):
    return ConnectFiveChallenge.objects.create(
        challenger=challenger,
        opponent=opponent,
        currency=currency,
        stake_amount=0,
        max_spend_amount=100,
        time_limit_seconds=300,
        expires_at=timezone.now(),
    )


def create_match(challenge):
    return ConnectFiveMatch.objects.create(
        challenge=challenge,
        player_a=challenge.challenger,
        player_b=challenge.opponent,
        active_player=challenge.challenger,
        clock_a_remaining_ms=300_000,
        clock_b_remaining_ms=300_000,
        max_spend_amount=challenge.max_spend_amount,
        time_limit_seconds=challenge.time_limit_seconds,
    )


@pytest.mark.django_db
@pytest.mark.parametrize('challenge_count', [1, 5])
def test_challenge_list_has_constant_queries(django_assert_num_queries, bucky, dmitry, tnb_currency, challenge_count):
    ConnectFiveStats.objects.create(user=bucky, elo=1234)
    match_ids = {}
    for _ in range(challenge_count):
        challenge = create_challenge(bucky, dmitry, tnb_currency)
        match_ids[challenge.id] = create_match(challenge).id
        pending_challenge = create_challenge(bucky, dmitry, tnb_currency)
        match_ids[pending_challenge.id] = None

    request = APIRequestFactory().get('/api/connect-five/challenges')
    force_authenticate(request, user=bucky)
    with django_assert_num_queries(2):
        response = ConnectFiveChallengeViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 200
    assert response.data['count'] == challenge_count * 2
    assert {item['id']: item['match_id'] for item in response.data['results']} == match_ids
    for challenge in response.data['results']:
        assert challenge['challenger']['connect_five_elo'] == 1234
        assert challenge['opponent']['connect_five_elo'] is None


@pytest.mark.django_db
@pytest.mark.parametrize('match_count', [1, 5])
def test_match_list_has_constant_queries(django_assert_num_queries, bucky, dmitry, tnb_currency, match_count):
    ConnectFiveStats.objects.create(user=bucky, elo=1234)
    matches = []
    for _ in range(match_count):
        match = create_match(create_challenge(bucky, dmitry, tnb_currency))
        ConnectFiveMatchPlayer.objects.create(match=match, user=bucky, spent_total=25)
        ConnectFiveMatchPlayer.objects.create(match=match, user=dmitry, spent_total=150)
        matches.append(match)

    request = APIRequestFactory().get('/api/connect-five/matches')
    force_authenticate(request, user=bucky)
    with django_assert_num_queries(3):
        response = ConnectFiveMatchViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 200
    assert response.data['count'] == match_count
    assert {item['id'] for item in response.data['results']} == {match.id for match in matches}
    for match in response.data['results']:
        assert match['active_player']['id'] == bucky.id
        assert match['player_a']['connect_five_elo'] == 1234
        assert match['player_b']['connect_five_elo'] is None
        players = {player['user']['id']: player for player in match['players']}
        assert players[bucky.id]['remaining_spend'] == 75
        assert players[bucky.id]['user']['connect_five_elo'] == 1234
        assert players[dmitry.id]['remaining_spend'] == 0
        assert players[dmitry.id]['user']['connect_five_elo'] is None


@pytest.mark.django_db
@pytest.mark.parametrize('message_count', [1, 5])
def test_match_chat_has_constant_queries(django_assert_num_queries, bucky, dmitry, tnb_currency, message_count):
    ConnectFiveStats.objects.create(user=bucky, elo=1234)
    match = create_match(create_challenge(bucky, dmitry, tnb_currency))
    for _ in range(message_count):
        ConnectFiveChatMessage.objects.create(match=match, sender=bucky, message='Hello')
        ConnectFiveChatMessage.objects.create(match=match, sender=dmitry, message='Hi')

    request = APIRequestFactory().get(f'/api/connect-five/matches/{match.id}/chat')
    force_authenticate(request, user=bucky)
    with django_assert_num_queries(3):
        response = ConnectFiveMatchViewSet.as_view({'get': 'chat'})(request, pk=match.id)

    assert response.status_code == 200
    assert response.data['count'] == message_count * 2
    for message in response.data['results']:
        sender = message['sender']
        assert sender['connect_five_elo'] == (1234 if sender['id'] == bucky.id else None)
