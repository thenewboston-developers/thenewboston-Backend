import importlib

import pytest
from django.apps import apps
from model_bakery import baker

from thenewboston.notifications.models import Notification
from thenewboston.social.models import Post

backfill = importlib.import_module('thenewboston.notifications.migrations.0003_add_post_owner_to_comment_mentions')


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
