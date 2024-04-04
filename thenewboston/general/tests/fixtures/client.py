import pytest
from rest_framework.test import APIClient


def _get_access_token(api_client, user):
    url = '/api/login'
    data = {
        'username': user.username,
        'password': 'pass1234',
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == 200, 'Login failed during test setup'
    return response.data['authentication']['access_token']


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def api_client_bucky(bucky):
    api_client = APIClient()  # we create own instance of `APIClient`, so `api_client` authentication is kept intact
    # TODO(dmu) LOW: Consider using `api_client.force_authenticate(bucky)`
    token = _get_access_token(api_client, bucky)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api_client
