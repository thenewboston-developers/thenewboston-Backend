import pytest


@pytest.mark.django_db
def test_create_manual_contribution_allowed_users(api_client):
    payload = {
        'invitation_code': 'fake',
        'username': 'fake',
        'password': 'FaKe1$jso3#@',
        'manual_contribution_reward_daily_limit': 100,
        'is_manual_contribution_allowed': True
    }
    response = api_client.post('/api/users', payload)
    assert response.status_code == 400
    assert response.json() == {
        'non_field_errors': [
            'Unknown field(s): is_manual_contribution_allowed, manual_contribution_reward_daily_limit'
        ]
    }
