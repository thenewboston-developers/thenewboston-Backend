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


def _build_authenticated_client(user):
    api_client = APIClient()
    token = _get_access_token(api_client, user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api_client


@pytest.fixture
def api_client_bucky(bucky):
    return _build_authenticated_client(bucky)


@pytest.fixture
def api_client_bucky_staff(bucky):
    bucky.is_staff = True
    bucky.save()
    return _build_authenticated_client(bucky)


@pytest.fixture
def authenticated_api_client(bucky):
    api_client = APIClient()  # we create own instance of `APIClient`, so `api_client` authentication is kept intact
    api_client.force_authenticate(bucky)
    api_client.forced_user = bucky
    return api_client
