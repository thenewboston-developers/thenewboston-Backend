import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from model_bakery import baker

from thenewboston.connect_five.models import ConnectFiveStats

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['/api/users', '/api/users/search?q=read_user'])
def test_user_read_queries_do_not_grow_with_result_size(authenticated_api_client, url):
    first = baker.make(User, username='read_user_0')
    baker.make(ConnectFiveStats, user=first, elo=1400)
    with CaptureQueriesContext(connection) as queries:
        response = authenticated_api_client.get(url)
    assert response.status_code == 200
    single_count = len(queries)
    for index in range(1, 8):
        baker.make(User, username=f'read_user_{index}')

    with CaptureQueriesContext(connection) as queries:
        response = authenticated_api_client.get(url)

    assert response.status_code == 200
    assert len(queries) == single_count
    assert single_count <= 3
    users = {user['id']: user for user in response.data}
    assert users[first.pk]['connect_five_elo'] == 1400
    assert all(user['connect_five_elo'] is None for user in response.data if user['id'] != first.pk)
    if 'search' in url:
        assert len(users) == 8


@pytest.mark.django_db
def test_user_update_accepts_users_without_game_stats(authenticated_api_client):
    user = authenticated_api_client.forced_user
    response = authenticated_api_client.patch(f'/api/users/{user.pk}', {'bio': 'Updated'}, format='multipart')

    assert response.status_code == 200
    assert response.data['bio'] == 'Updated'
    assert response.data['connect_five_elo'] is None
