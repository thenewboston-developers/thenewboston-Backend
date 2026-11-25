from django.db.models import Q, QuerySet
from django.db.models.signals import post_delete

from thenewboston.general.enums import NotificationType
from thenewboston.notifications.models import Notification

from .models import Comment, Post


def is_post_deletion(origin):
    """Whether a deletion started from one or more posts, which take the notifications of their comments along."""
    if isinstance(origin, QuerySet):
        return issubclass(origin.model, Post)

    return isinstance(origin, Post)


def delete_post_notifications(sender, instance, **kwargs):
    # Every notification about a post or one of its comments stores the id of the post
    Notification.objects.filter(payload__post_id=instance.pk).delete()


def delete_comment_notifications(sender, instance, origin=None, **kwargs):
    if is_post_deletion(origin):
        return  # Removed by `delete_post_notifications()`, with one query for the whole post

    # POST_COMMENT notifications created before 2026-01-03 store the comment as text, not its id, so only the deletion of
    # their post removes them
    Notification.objects.filter(
        Q(payload__notification_type=NotificationType.COMMENT_MENTION.value, payload__comment_id=instance.pk)
        | Q(payload__notification_type=NotificationType.POST_COMMENT.value, payload__comment__id=instance.pk)
    ).delete()


def connect_signals():
    # Notifications keep a snapshot of the post or comment instead of a foreign key. Without these receivers deleting
    # either one (through the API, the admin or the deletion of an account) leaves notifications that lead nowhere.
    post_delete.connect(delete_post_notifications, sender=Post, dispatch_uid='social.delete_post_notifications')
    post_delete.connect(
        delete_comment_notifications, sender=Comment, dispatch_uid='social.delete_comment_notifications'
    )
