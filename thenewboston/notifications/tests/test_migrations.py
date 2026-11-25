import importlib

import pytest
from django.apps import apps
from model_bakery import baker

from thenewboston.notifications.models import Notification
from thenewboston.social.models import Comment, Post

backfill = importlib.import_module('thenewboston.notifications.migrations.0003_add_post_owner_to_comment_mentions')
cleanup = importlib.import_module(
    'thenewboston.notifications.migrations.0004_delete_notifications_of_deleted_posts_and_comments'
)


@pytest.mark.django_db
def test_comment_mentions_created_before_the_post_owner_was_stored_get_it(bucky):
    post_owner = baker.make('users.User', username='post_owner')
    post = baker.make(Post, owner=post_owner)
    deleted_post = baker.make(Post, owner=post_owner)
    deleted_post_id = deleted_post.pk
    deleted_post.delete()

    def create(payload):
        return Notification.objects.create(owner=bucky, payload=payload)

    missing = [create({'notification_type': 'COMMENT_MENTION', 'post_id': post.pk}) for _ in range(3)]
    post_gone = create({'notification_type': 'COMMENT_MENTION', 'post_id': deleted_post_id})
    named = create(
        {'notification_type': 'COMMENT_MENTION', 'post_id': post.pk, 'post_owner': {'id': 1, 'username': 'kept'}}
    )
    other_type = create({'notification_type': 'POST_COMMENT', 'post_id': post.pk})

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(backfill, 'BATCH_SIZE', 2)  # Covers a full batch and the remainder
        backfill.add_post_owner_to_comment_mentions(apps, None)

    for notification in missing:
        notification.refresh_from_db()
        assert notification.payload == {
            'notification_type': 'COMMENT_MENTION',
            'post_id': post.pk,
            'post_owner': {'id': post_owner.pk, 'username': 'post_owner'},
        }
    for notification, payload in (
        (post_gone, {'notification_type': 'COMMENT_MENTION', 'post_id': deleted_post_id}),
        (
            named,
            {'notification_type': 'COMMENT_MENTION', 'post_id': post.pk, 'post_owner': {'id': 1, 'username': 'kept'}},
        ),
        (other_type, {'notification_type': 'POST_COMMENT', 'post_id': post.pk}),
    ):
        notification.refresh_from_db()
        assert notification.payload == payload


@pytest.mark.django_db
def test_notifications_whose_post_or_comment_was_deleted_are_deleted(bucky):
    post = baker.make(Post, owner=bucky)
    comment = baker.make(Comment, owner=bucky, post=post, price_amount=None, price_currency=None)
    deleted_post = baker.make(Post, owner=bucky)
    deleted_comment = baker.make(Comment, owner=bucky, post=post, price_amount=None, price_currency=None)
    deleted_post_id, deleted_comment_id = deleted_post.pk, deleted_comment.pk
    deleted_post.delete()
    deleted_comment.delete()

    def create(notification_type, **payload):
        return Notification.objects.create(owner=bucky, payload={'notification_type': notification_type, **payload})

    deleted = [
        create('POST_LIKE', post_id=deleted_post_id),
        create('POST_COIN_TRANSFER', post_id=deleted_post_id),
        create('POST_COMMENT', post_id=deleted_post_id, comment='Stored as text before 2026-01-03'),
        create('POST_COMMENT', post_id=post.pk, comment={'id': deleted_comment_id}),
        create('COMMENT_MENTION', post_id=post.pk, comment_id=deleted_comment_id, comment={'id': deleted_comment_id}),
        create('COMMENT_MENTION', post_id=post.pk, comment_id=deleted_comment_id, comment='Stored as text'),
    ]
    kept = [
        create('POST_LIKE', post_id=post.pk),
        create('POST_COMMENT', post_id=post.pk, comment={'id': comment.pk}),
        create('COMMENT_MENTION', post_id=post.pk, comment_id=comment.pk, comment={'id': comment.pk}),
        # Its comment cannot be told apart from the others without an id
        create('POST_COMMENT', post_id=post.pk, comment='Stored as text before 2026-01-03'),
        # Only notifications about comments point at one
        create('POST_LIKE', post_id=post.pk, comment_id=deleted_comment_id),
        create('PROFILE_FOLLOW'),
        create('POST_LIKE', post_id=None),
    ]

    def remaining():
        return set(Notification.objects.values_list('id', flat=True))

    assert remaining() == {notification.id for notification in deleted + kept}

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(cleanup, 'BATCH_SIZE', 2)  # Covers full batches and the remainder
        cleanup.delete_notifications_of_deleted_posts_and_comments(apps, None)

    assert remaining() == {notification.id for notification in kept}
