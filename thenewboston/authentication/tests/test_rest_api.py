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
        'bio': '',
        'discord_username': None,
        'facebook_username': None,
        'github_username': None,
        'id': bucky.id,
        'instagram_username': None,
        'is_staff': False,
        'linkedin_username': None,
        'pinterest_username': None,
        'reddit_username': None,
        'tiktok_username': None,
        'twitch_username': None,
        'username': bucky.username,
        'x_username': None,
        'youtube_username': None,
    }
