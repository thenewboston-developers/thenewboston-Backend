from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.utils.text import truncate_text
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.notifications.models.notification import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.users.serializers.user import UserReadSerializer


def notify_mentioned_users_in_post(post, mentioned_user_ids, request):
    """
    Create notifications for users mentioned in a post.

    Args:
        post: The Post instance containing mentions
        mentioned_user_ids: List of user IDs to notify
        request: The HTTP request object for context
    """
    for user_id in mentioned_user_ids:
        # Skip notifying the post owner (don't notify yourself)
        if user_id == post.owner.id:
            continue

        notification = Notification.objects.create(
            owner_id=user_id,
            payload={
                'post_id': post.id,
                'mentioner': UserReadSerializer(post.owner, context={'request': request}).data,
                'notification_type': NotificationType.POST_MENTION.value,
                'post_preview': truncate_text(post.content),
                'post_image_thumbnail': request.build_absolute_uri(post.image.url) if post.image else None,
                'post_created': post.created_date.isoformat(),
            },
        )

        notification_data = NotificationReadSerializer(notification, context={'request': request}).data

        NotificationConsumer.stream_notification(
            message_type=MessageType.CREATE_NOTIFICATION, notification_data=notification_data
        )


def notify_mentioned_users_in_comment(comment, mentioned_user_ids, request):
    """
    Create notifications for users mentioned in a comment.

    Args:
        comment: The Comment instance containing mentions
        mentioned_user_ids: List of user IDs to notify
        request: The HTTP request object for context
    """
    post = comment.post

    for user_id in mentioned_user_ids:
        # Skip notifying the comment owner (don't notify yourself)
        if user_id == comment.owner.id:
            continue

        notification = Notification.objects.create(
            owner_id=user_id,
            payload={
                'post_id': post.id,
                'comment_id': comment.id,
                'mentioner': UserReadSerializer(comment.owner, context={'request': request}).data,
                'comment': comment.content,
                'notification_type': NotificationType.COMMENT_MENTION.value,
                'post_preview': truncate_text(post.content),
                'comment_preview': truncate_text(comment.content),
                'post_image_thumbnail': request.build_absolute_uri(post.image.url) if post.image else None,
                'post_created': post.created_date.isoformat(),
            },
        )

        notification_data = NotificationReadSerializer(notification, context={'request': request}).data

        NotificationConsumer.stream_notification(
            message_type=MessageType.CREATE_NOTIFICATION, notification_data=notification_data
        )
