from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from model_bakery import baker

from thenewboston.notifications.models import Notification
from thenewboston.social.models import Comment, Post

User = get_user_model()


def ids_of(notifications):
    return {notification.id for notification in notifications}


def make_comment(owner, post):
    return baker.make(Comment, owner=owner, post=post, price_amount=None, price_currency=None)


def notification_ids():
    return set(Notification.objects.values_list('id', flat=True))


def notify(owner, notification_type, **payload):
    return Notification.objects.create(owner=owner, payload={'notification_type': notification_type, **payload})


@pytest.fixture
def comment_through_api(authenticated_api_client, django_capture_on_commit_callbacks):
    """Comments as the app does and returns the id of the comment with the ids of the notifications it created."""

    def comment(post, content):
        existing_ids = notification_ids()
        # Patching the class attribute covers the comment view as well as the mention helpers
        with patch('thenewboston.social.utils.mentions.NotificationConsumer.stream_notification'):
            with django_capture_on_commit_callbacks(execute=True):
                response = authenticated_api_client.post(
                    '/api/comments', {'content': content, 'post': post.pk}, format='json'
                )
        assert response.status_code == 201, response.data
        return response.data['id'], notification_ids() - existing_ids

    return comment


@pytest.mark.django_db
class TestDeletingAPost:
    def test_removes_the_notifications_about_the_post_and_its_comments(self, authenticated_api_client):
        bucky = authenticated_api_client.forced_user
        friend = baker.make(User, username='friend')
        post = baker.make(Post, owner=bucky)
        other_post = baker.make(Post, owner=bucky)
        comment = make_comment(friend, post)
        removed = [
            notify(bucky, 'POST_LIKE', post_id=post.pk),
            notify(friend, 'POST_MENTION', post_id=post.pk),
            notify(friend, 'POST_COIN_TRANSFER', post_id=post.pk),
            notify(bucky, 'POST_COMMENT', post_id=post.pk, comment={'id': comment.pk}),
            notify(bucky, 'POST_COMMENT', post_id=post.pk, comment='Stored as text before 2026-01-03'),
            notify(friend, 'COMMENT_MENTION', post_id=post.pk, comment_id=comment.pk, comment={'id': comment.pk}),
        ]
        kept = [
            notify(bucky, 'POST_LIKE', post_id=other_post.pk),
            notify(bucky, 'PROFILE_FOLLOW', follower={'id': friend.pk}),
        ]
        assert notification_ids() == ids_of(removed + kept)

        response = authenticated_api_client.delete(f'/api/posts/{post.pk}')

        assert response.status_code == 204
        assert notification_ids() == ids_of(kept)

    def test_deleting_several_posts_at_once_removes_the_notifications_about_each(self, bucky):
        deleted_posts = baker.make(Post, owner=bucky, _quantity=2)
        other_post = baker.make(Post, owner=bucky)
        for post in deleted_posts:
            notify(bucky, 'POST_LIKE', post_id=post.pk)
            comment = make_comment(bucky, post)
            notify(bucky, 'COMMENT_MENTION', post_id=post.pk, comment_id=comment.pk, comment={'id': comment.pk})
        kept = notify(bucky, 'POST_LIKE', post_id=other_post.pk)

        # As the admin does when several posts are selected
        Post.objects.filter(id__in=[post.id for post in deleted_posts]).delete()

        assert notification_ids() == {kept.id}

    @pytest.mark.parametrize(
        'delete',
        [lambda post: post.delete(), lambda post: Post.objects.filter(id=post.id).delete()],
        ids=['instance', 'queryset'],
    )
    def test_one_query_removes_the_notifications_of_the_post_and_all_of_its_comments(self, bucky, delete):
        post = baker.make(Post, owner=bucky)
        for comment in [make_comment(bucky, post) for _ in range(3)]:
            notify(bucky, 'POST_COMMENT', post_id=post.pk, comment={'id': comment.pk})

        with CaptureQueriesContext(connection) as context:
            delete(post)

        notification_deletes = [
            query
            for query in context.captured_queries
            if query['sql'].startswith('DELETE FROM "notifications_notification"')
        ]
        assert len(notification_deletes) == 1
        assert not Notification.objects.exists()

    def test_deleting_an_account_removes_the_notifications_about_its_posts_and_comments(self, bucky):
        leaving_user = baker.make(User, username='leaving_user')
        their_post = baker.make(Post, owner=leaving_user)
        bucky_post = baker.make(Post, owner=bucky)
        their_comment = make_comment(leaving_user, bucky_post)
        bucky_comment = make_comment(bucky, bucky_post)
        removed = [
            notify(bucky, 'POST_MENTION', post_id=their_post.pk),
            notify(bucky, 'POST_COMMENT', post_id=bucky_post.pk, comment={'id': their_comment.pk}),
        ]
        kept = [
            notify(bucky, 'POST_LIKE', post_id=bucky_post.pk),
            notify(bucky, 'POST_COMMENT', post_id=bucky_post.pk, comment={'id': bucky_comment.pk}),
        ]
        assert notification_ids() == ids_of(removed + kept)

        leaving_user.delete()

        assert notification_ids() == ids_of(kept)


@pytest.mark.django_db
class TestDeletingAComment:
    def test_removes_the_notifications_about_the_comment(self, authenticated_api_client, comment_through_api):
        post_owner = baker.make(User, username='post_owner')
        baker.make(User, username='mentioned_user')
        post = baker.make(Post, owner=post_owner)
        deleted_comment_id, removed_ids = comment_through_api(post, 'Look @mentioned_user')
        _, kept_ids = comment_through_api(post, 'Again @mentioned_user')
        kept = [
            notify(post_owner, 'POST_LIKE', post_id=post.pk),
            # Without the id of its comment it cannot be told apart from the others, so it goes only with the post
            notify(post_owner, 'POST_COMMENT', post_id=post.pk, comment='Look @mentioned_user'),
        ]
        assert len(removed_ids) == 2  # POST_COMMENT for the post owner and COMMENT_MENTION for the mentioned user

        response = authenticated_api_client.delete(f'/api/comments/{deleted_comment_id}')

        assert response.status_code == 204
        assert notification_ids() == kept_ids | ids_of(kept)

    def test_deleting_several_comments_at_once_removes_the_notifications_about_each(self, bucky):
        post = baker.make(Post, owner=bucky)
        deleted_comments = [make_comment(bucky, post) for _ in range(2)]
        kept_comment = make_comment(bucky, post)
        for comment in deleted_comments:
            notify(bucky, 'POST_COMMENT', post_id=post.pk, comment={'id': comment.pk})
            # Stored as text until 2026-01-03, with the id of the comment next to it
            notify(bucky, 'COMMENT_MENTION', post_id=post.pk, comment_id=comment.pk, comment='Look @bucky')
        kept = notify(bucky, 'POST_COMMENT', post_id=post.pk, comment={'id': kept_comment.pk})

        # As the admin does when several comments are selected
        Comment.objects.filter(id__in=[comment.id for comment in deleted_comments]).delete()

        assert notification_ids() == {kept.id}
