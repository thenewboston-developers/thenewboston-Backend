from django.db import migrations

BATCH_SIZE = 1000

# Where the notifications about a comment store its id. POST_COMMENT notifications created before 2026-01-03 store the
# comment as text instead, so they are deleted only when their post is gone.
COMMENT_ID_KEYS = {'COMMENT_MENTION': 'payload__comment_id', 'POST_COMMENT': 'payload__comment__id'}


def as_id(value):
    """The value when it is an id (payloads store ids as JSON numbers), otherwise None."""
    return value if type(value) is int else None


def delete_notifications_of_deleted_posts_and_comments(apps, schema_editor):
    """Delete the notifications whose post or comment no longer exists, as deleting a post or comment now does."""
    Comment = apps.get_model('social', 'Comment')
    Notification = apps.get_model('notifications', 'Notification')
    Post = apps.get_model('social', 'Post')

    rows = (
        Notification.objects.filter(payload__has_key='post_id')
        .order_by('id')
        .values('id', 'payload__notification_type', 'payload__post_id', *COMMENT_ID_KEYS.values())
    )

    def delete_orphans(batch):
        post_ids = {post_id for _, post_id, _ in batch}
        comment_ids = {comment_id for *_, comment_id in batch if comment_id is not None}
        existing_post_ids = set(Post.objects.filter(id__in=post_ids).values_list('id', flat=True))
        existing_comment_ids = set(Comment.objects.filter(id__in=comment_ids).values_list('id', flat=True))
        orphan_ids = [
            notification_id
            for notification_id, post_id, comment_id in batch
            if post_id not in existing_post_ids or (comment_id is not None and comment_id not in existing_comment_ids)
        ]
        Notification.objects.filter(id__in=orphan_ids).delete()

    batch = []
    for row in rows.iterator(chunk_size=BATCH_SIZE):
        post_id = as_id(row['payload__post_id'])
        if post_id is None:
            continue  # Not a payload this migration knows, so it is left alone

        comment_id_key = COMMENT_ID_KEYS.get(row['payload__notification_type'])
        comment_id = as_id(row[comment_id_key]) if comment_id_key else None
        batch.append((row['id'], post_id, comment_id))
        if len(batch) >= BATCH_SIZE:
            delete_orphans(batch)
            batch = []

    if batch:
        delete_orphans(batch)


class Migration(migrations.Migration):
    dependencies = [
        ('notifications', '0003_add_post_owner_to_comment_mentions'),
        ('social', '0009_remove_post_image'),
    ]

    operations = [
        # Deleted notifications cannot be brought back, and leaving them in place is what this migration fixes
        migrations.RunPython(delete_notifications_of_deleted_posts_and_comments, migrations.RunPython.noop),
    ]
