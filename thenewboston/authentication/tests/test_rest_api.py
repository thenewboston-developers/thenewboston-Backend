import pytest


@pytest.mark.django_db
def test_login(api_client, bucky):
    url = '/api/login'
    data = {'username': bucky.username, 'password': 'pass1234'}
    response = api_client.post(url, data, format='json')
    assert response.status_code == 200

    expected_keys = ['authentication', 'user']
    assert all(key in response.data for key in expected_keys)

    expected_user_keys = ['id', 'username']
    assert all(key in response.data['user'] for key in expected_user_keys)
