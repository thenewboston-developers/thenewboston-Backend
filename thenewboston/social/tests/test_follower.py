import pytest
from django.contrib.auth import get_user_model
from model_bakery import baker
from rest_framework import status

from thenewboston.notifications.models import Notification
from thenewboston.social.models import Follower

User = get_user_model()


@pytest.mark.django_db
class TestFollowerViewSet:
    def test_unauthenticated_user_cannot_create_follower(self, api_client):
        """Test that unauthenticated users cannot follow others."""
        user_to_follow = baker.make(User)

        response = api_client.post('/api/followers', {'following': user_to_follow.id})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_authenticated_user_can_follow_another_user(self, authenticated_api_client):
        """Test successful follow and notification creation."""
        user_to_follow = baker.make(User)

        initial_notification_count = Notification.objects.count()

        response = authenticated_api_client.post('/api/followers', {'following': user_to_follow.id})

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['follower']['id'] == authenticated_api_client.forced_user.id
        assert response.data['following']['id'] == user_to_follow.id

        # Verify follower relationship was created
        assert Follower.objects.filter(follower=authenticated_api_client.forced_user, following=user_to_follow).exists()

        # Verify notification was created for the followed user
        assert Notification.objects.count() == initial_notification_count + 1
        notification = Notification.objects.latest('created_date')
        assert notification.owner == user_to_follow
        assert notification.payload['notification_type'] == 'PROFILE_FOLLOW'
        assert notification.payload['follower']['id'] == authenticated_api_client.forced_user.id

    def test_user_cannot_follow_themselves(self, authenticated_api_client):
        """Test that users cannot follow themselves."""
        user = authenticated_api_client.forced_user

        response = authenticated_api_client.post('/api/followers', {'following': user.id})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'You cannot follow yourself' in str(response.data)

        # Verify no follower relationship was created
        assert not Follower.objects.filter(follower=user, following=user).exists()

        # Verify no notification was created
        assert Notification.objects.filter(owner=user).count() == 0

    def test_user_cannot_follow_same_user_twice(self, authenticated_api_client):
        """Test that duplicate follow relationships are prevented."""
        user_to_follow = baker.make(User)

        # First follow - should succeed
        response1 = authenticated_api_client.post('/api/followers', {'following': user_to_follow.id})
        assert response1.status_code == status.HTTP_201_CREATED

        # Second follow attempt - should fail
        response2 = authenticated_api_client.post('/api/followers', {'following': user_to_follow.id})
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
        assert 'This relationship already exists' in str(response2.data)

        # Verify only one relationship exists
        assert (
            Follower.objects.filter(follower=authenticated_api_client.forced_user, following=user_to_follow).count()
            == 1
        )

        # Verify only one notification was created
        assert Notification.objects.filter(owner=user_to_follow).count() == 1

    def test_user_can_unfollow(self, authenticated_api_client):
        """Test that users can unfollow others."""
        user_to_follow = baker.make(User)

        # Create follow relationship
        Follower.objects.create(follower=authenticated_api_client.forced_user, following=user_to_follow)

        # Unfollow
        response = authenticated_api_client.delete(f'/api/followers/{user_to_follow.id}')

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Follower.objects.filter(
            follower=authenticated_api_client.forced_user, following=user_to_follow
        ).exists()

    def test_user_can_follow_multiple_users(self, authenticated_api_client):
        """Test that a user can follow multiple different users."""
        user1 = baker.make(User)
        user2 = baker.make(User)

        # Follow user1
        response1 = authenticated_api_client.post('/api/followers', {'following': user1.id})
        assert response1.status_code == status.HTTP_201_CREATED

        # Follow user2
        response2 = authenticated_api_client.post('/api/followers', {'following': user2.id})
        assert response2.status_code == status.HTTP_201_CREATED

        # Verify both relationships exist
        assert Follower.objects.filter(follower=authenticated_api_client.forced_user).count() == 2
        assert Follower.objects.filter(follower=authenticated_api_client.forced_user, following=user1).exists()
        assert Follower.objects.filter(follower=authenticated_api_client.forced_user, following=user2).exists()

        # Verify notifications were created for both users
        assert Notification.objects.filter(owner=user1).count() == 1
        assert Notification.objects.filter(owner=user2).count() == 1

    def test_multiple_users_can_follow_same_user(self, api_client):
        """Test that multiple users can follow the same user."""
        user1 = baker.make(User)
        user2 = baker.make(User)
        target_user = baker.make(User)

        # User1 follows target_user
        api_client.force_authenticate(user=user1)
        response1 = api_client.post('/api/followers', {'following': target_user.id})
        assert response1.status_code == status.HTTP_201_CREATED

        # User2 follows target_user
        api_client.force_authenticate(user=user2)
        response2 = api_client.post('/api/followers', {'following': target_user.id})
        assert response2.status_code == status.HTTP_201_CREATED

        # Verify both relationships exist
        assert Follower.objects.filter(following=target_user).count() == 2

        # Verify target_user received notifications from both followers
        notifications = Notification.objects.filter(owner=target_user).order_by('created_date')
        assert notifications.count() == 2
        assert notifications[0].payload['follower']['id'] == user1.id
        assert notifications[1].payload['follower']['id'] == user2.id

    def test_list_followers(self, api_client):
        """Test listing followers with self_following field."""
        user1 = baker.make(User)
        user2 = baker.make(User)
        user3 = baker.make(User)

        # user2 and user3 follow user1
        Follower.objects.create(follower=user2, following=user1)
        Follower.objects.create(follower=user3, following=user1)

        # user2 also follows user3
        Follower.objects.create(follower=user2, following=user3)

        # Request as user2
        api_client.force_authenticate(user=user2)
        response = api_client.get(f'/api/followers?following={user1.id}')

        assert response.status_code == status.HTTP_200_OK
        results = response.data['results']
        assert len(results) == 2

        # Check self_following field
        for result in results:
            if result['follower']['id'] == user3.id:
                # user2 follows user3
                assert result['self_following'] is True
            elif result['follower']['id'] == user2.id:
                # user2 looking at themselves
                assert result['self_following'] is False

    def test_follower_notification_payload_structure(self, authenticated_api_client):
        """Test that notification payload has correct structure."""
        user_to_follow = baker.make(User)

        response = authenticated_api_client.post('/api/followers', {'following': user_to_follow.id})
        assert response.status_code == status.HTTP_201_CREATED

        notification = Notification.objects.get(owner=user_to_follow)

        # Verify payload structure
        assert 'notification_type' in notification.payload
        assert 'follower' in notification.payload
        assert notification.payload['notification_type'] == 'PROFILE_FOLLOW'

        # Verify follower data includes essential fields
        follower_data = notification.payload['follower']
        assert 'id' in follower_data
        assert 'username' in follower_data
        assert follower_data['id'] == authenticated_api_client.forced_user.id
        assert follower_data['username'] == authenticated_api_client.forced_user.username

    def test_follow_nonexistent_user(self, authenticated_api_client):
        """Test that following a non-existent user fails gracefully."""
        response = authenticated_api_client.post('/api/followers', {'following': 99999})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_notification_not_created_for_invalid_follow(self, authenticated_api_client):
        """Test that notifications are not created when follow validation fails."""
        user = authenticated_api_client.forced_user
        initial_notification_count = Notification.objects.count()

        # Try to follow self (should fail)
        response = authenticated_api_client.post('/api/followers', {'following': user.id})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Verify no notification was created
        assert Notification.objects.count() == initial_notification_count

    def test_follower_and_following_user_details_in_response(self, authenticated_api_client):
        """Test that the API response includes full user details for follower and following."""
        user_to_follow = baker.make(User, username='target_user')

        response = authenticated_api_client.post('/api/followers', {'following': user_to_follow.id})

        assert response.status_code == status.HTTP_201_CREATED

        # Check follower details in response
        assert 'follower' in response.data
        assert response.data['follower']['id'] == authenticated_api_client.forced_user.id
        assert response.data['follower']['username'] == authenticated_api_client.forced_user.username

        # Check following details in response
        assert 'following' in response.data
        assert response.data['following']['id'] == user_to_follow.id
        assert response.data['following']['username'] == 'target_user'
