from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from model_bakery import baker

from thenewboston.notifications.models import Notification
from thenewboston.social.models import Comment, Post

User = get_user_model()


@pytest.fixture
def send_comment(authenticated_api_client, django_capture_on_commit_callbacks):
    def send(method, url, data):
        # Patching the class attribute covers the comment view as well as the mention helpers
        with patch('thenewboston.social.utils.mentions.NotificationConsumer.stream_notification'):
            with django_capture_on_commit_callbacks(execute=True):
                response = getattr(authenticated_api_client, method)(url, data, format='json')
        assert response.status_code in (200, 201), response.data
        return response.data

    return send


@pytest.mark.django_db
class TestCommentNotifications:
    def test_mention_on_someone_elses_post_names_the_post_owner(self, send_comment):
        post_owner = baker.make(User, username='post_owner')
        mentioned_user = baker.make(User, username='mentioned_user')
        post = baker.make(Post, owner=post_owner, content='Original post')

        comment = send_comment('post', '/api/comments', {'content': '@mentioned_user look', 'post': post.pk})

        payload = Notification.objects.get(owner=mentioned_user).payload
        assert payload['notification_type'] == 'COMMENT_MENTION'
        assert payload['post_owner'] == {'id': post_owner.pk, 'username': 'post_owner'}
        assert payload['comment']['id'] == comment['id']
        assert payload['post_preview'] == 'Original post'
        assert Notification.objects.get(owner=post_owner).payload['notification_type'] == 'POST_COMMENT'

    def test_post_owner_mentioned_on_their_own_post_gets_one_notification_that_says_so(self, send_comment):
        post_owner = baker.make(User, username='post_owner')
        post = baker.make(Post, owner=post_owner, content='Original post')

        send_comment('post', '/api/comments', {'content': 'Thanks @post_owner', 'post': post.pk})

        payloads = list(Notification.objects.filter(owner=post_owner).values_list('payload', flat=True))
        assert [payload['notification_type'] for payload in payloads] == ['COMMENT_MENTION']
        assert payloads[0]['post_owner'] == {'id': post_owner.pk, 'username': 'post_owner'}

    def test_mention_added_by_an_edit_names_the_post_owner(self, authenticated_api_client, send_comment):
        post_owner = baker.make(User, username='post_owner')
        mentioned_user = baker.make(User, username='mentioned_user')
        post = baker.make(Post, owner=post_owner)
        comment = baker.make(
            Comment,
            content='No mention yet',
            owner=authenticated_api_client.forced_user,
            post=post,
            price_amount=None,
            price_currency=None,
        )

        send_comment('patch', f'/api/comments/{comment.pk}', {'content': 'Now @mentioned_user'})

        payload = Notification.objects.get(owner=mentioned_user).payload
        assert payload['post_owner'] == {'id': post_owner.pk, 'username': 'post_owner'}
        assert payload['comment']['content'] == 'Now @mentioned_user'
