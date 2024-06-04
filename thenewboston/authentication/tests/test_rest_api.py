import pytest


@pytest.mark.django_db
def test_login(api_client, bucky):
    url = '/api/login'
    data = {'username': bucky.username, 'password': 'pass1234'}
    response = api_client.post(url, data, format='json')
    assert response.status_code == 200

    expected_keys = ['authentication', 'user']
    assert all(key in response.data for key in expected_keys)

    expected_authentication_keys = ['access_token', 'refresh_token']
    assert all(key in response.data['authentication'] for key in expected_authentication_keys)

    assert response.data['user'] == {
        'avatar': None,
        'id': bucky.id,
        'is_manual_contribution_allowed': bucky.is_manual_contribution_allowed,
        'username': bucky.username,
    }
