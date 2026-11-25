from django.db import migrations

BATCH_SIZE = 500


def add_post_owner_to_comment_mentions(apps, schema_editor):
    """
    Name the owner of the post in comment mention notifications that were created before the payload carried it.

    Notifications whose post was deleted keep their payload as it is.
    """
    Notification = apps.get_model('notifications', 'Notification')
    Post = apps.get_model('social', 'Post')

    notifications = (
        Notification.objects.filter(payload__notification_type='COMMENT_MENTION')
        .exclude(payload__has_key='post_owner')
        .only('id', 'payload')
        .order_by('id')
    )
    batch = []

    def update(batch):
        post_ids = {notification.payload.get('post_id') for notification in batch}
        owners = {
            post_id: {'id': owner_id, 'username': username}
            for post_id, owner_id, username in Post.objects.filter(id__in=post_ids).values_list(
                'id', 'owner_id', 'owner__username'
            )
        }
        changed = []
        for notification in batch:
            owner = owners.get(notification.payload.get('post_id'))
            if owner is not None:
                notification.payload['post_owner'] = owner
                changed.append(notification)

        Notification.objects.bulk_update(changed, ['payload'])

    for notification in notifications.iterator(chunk_size=BATCH_SIZE):
        batch.append(notification)
        if len(batch) >= BATCH_SIZE:
            update(batch)
            batch = []

    if batch:
        update(batch)


class Migration(migrations.Migration):
    dependencies = [
        ('notifications', '0002_initial'),
        ('social', '0009_remove_post_image'),
    ]

    operations = [
        # Nothing to undo: the frontend reads the added key only when it is there
        migrations.RunPython(add_post_owner_to_comment_mentions, migrations.RunPython.noop),
    ]
