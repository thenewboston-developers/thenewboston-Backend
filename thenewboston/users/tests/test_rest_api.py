import pytest
from django.contrib.auth import get_user_model
from model_bakery import baker

User = get_user_model()


@pytest.mark.django_db
def test_anonymous_user_can_read_user(api_client, bucky):
    response = api_client.get(f'/api/users/{bucky.pk}')

    assert response.status_code == 200
    assert response.data['id'] == bucky.pk
    assert response.data['username'] == 'bucky'
    assert 'email' not in response.data
    assert 'password' not in response.data


@pytest.mark.django_db
def test_anonymous_user_can_read_user_stats(api_client, bucky, dmitry, bucky_tnb_wallet):
    baker.make('social.Follower', follower=dmitry, following=bucky)

    response = api_client.get(f'/api/user/{bucky.pk}/stats')

    assert response.status_code == 200
    assert response.data == {
        'id': bucky.pk,
        'default_wallet_balance': bucky_tnb_wallet.balance,
        'followers_count': 1,
        'following_count': 0,
    }


@pytest.mark.django_db
def test_anonymous_user_cannot_search_users(api_client, bucky):
    response = api_client.get('/api/users/search?q=buc')

    assert response.status_code == 401


@pytest.mark.django_db
def test_anonymous_user_cannot_update_user(api_client, bucky):
    response = api_client.patch(f'/api/users/{bucky.pk}', {'bio': 'Hacked'}, format='multipart')

    assert response.status_code == 401
    bucky.refresh_from_db()
    assert bucky.bio == ''


@pytest.mark.django_db
def test_user_cannot_update_another_user(authenticated_api_client, dmitry):
    response = authenticated_api_client.patch(f'/api/users/{dmitry.pk}', {'bio': 'Hacked'}, format='multipart')

    assert response.status_code == 403
    dmitry.refresh_from_db()
    assert dmitry.bio == ''


@pytest.mark.django_db
def test_anonymous_user_cannot_delete_user(api_client, bucky):
    response = api_client.delete(f'/api/users/{bucky.pk}')

    assert response.status_code in (401, 405)
    assert User.objects.filter(pk=bucky.pk).exists()


@pytest.mark.django_db
def test_user_cannot_delete_another_user(authenticated_api_client, dmitry):
    response = authenticated_api_client.delete(f'/api/users/{dmitry.pk}')

    assert response.status_code == 405
    assert User.objects.filter(pk=dmitry.pk).exists()


@pytest.mark.django_db
def test_user_cannot_delete_self(authenticated_api_client):
    user = authenticated_api_client.forced_user

    response = authenticated_api_client.delete(f'/api/users/{user.pk}')

    assert response.status_code == 405
    assert User.objects.filter(pk=user.pk).exists()
