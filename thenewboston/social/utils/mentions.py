import re
from typing import List, Optional, Sequence, Set

from rest_framework import serializers

from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.utils.text import truncate_text
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.notifications.models.notification import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.users.models import User
from thenewboston.users.serializers.user import UserReadSerializer

MENTION_PATTERN = re.compile(r'@(\w+)')


def extract_usernames_from_text(content: str) -> Set[str]:
    if not content:
        return set()

    return {match.group(1).lower() for match in MENTION_PATTERN.finditer(content)}


def validate_mentioned_user_ids(*, content: str, mentioned_user_ids: Sequence[int]) -> List[int]:
    if mentioned_user_ids is None:
        return []

    unique_ids: List[int] = []
    seen = set()
    for user_id in mentioned_user_ids:
        if user_id not in seen:
            seen.add(user_id)
            unique_ids.append(user_id)

    users = list(User.objects.filter(id__in=unique_ids))
    users_by_id = {user.id: user for user in users}

    missing_ids = [str(user_id) for user_id in unique_ids if user_id not in users_by_id]
    if missing_ids:
        raise serializers.ValidationError({'mentioned_user_ids': f'Invalid user ids: {", ".join(missing_ids)}'})

    mentioned_usernames = extract_usernames_from_text(content)
    invalid_usernames = [
        users_by_id[user_id].username
        for user_id in unique_ids
        if users_by_id[user_id].username.lower() not in mentioned_usernames
    ]

    if invalid_usernames:
        raise serializers.ValidationError(
            {
                'mentioned_user_ids': (
                    f'The following users were not mentioned in the content: {", ".join(invalid_usernames)}'
                )
            }
        )

    return unique_ids


def derive_mentioned_user_ids(content: str) -> List[int]:
    usernames = list(extract_usernames_from_text(content))
    if not usernames:
        return []

    mention_ids: List[int] = []
    seen_ids = set()

    for username in usernames:
        user = User.objects.filter(username__iexact=username).first()
        if user and user.id not in seen_ids:
            seen_ids.add(user.id)
            mention_ids.append(user.id)

    return mention_ids


def sync_mentioned_users(*, instance, content: str, mentioned_user_ids: Optional[Sequence[int]]):
    if mentioned_user_ids is None:
        validated_ids = derive_mentioned_user_ids(content)
    else:
        validated_ids = validate_mentioned_user_ids(content=content, mentioned_user_ids=mentioned_user_ids)

    previous_ids = set(instance.mentioned_users.values_list('id', flat=True))
    instance.mentioned_users.set(validated_ids)

    new_mentions = list(set(validated_ids) - previous_ids)
    if new_mentions:
        instance._new_mention_ids = new_mentions
    elif hasattr(instance, '_new_mention_ids'):
        delattr(instance, '_new_mention_ids')

    return validated_ids


def notify_mentioned_users_in_post(post, mentioned_user_ids, request):
    for user_id in mentioned_user_ids:
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
    post = comment.post

    for user_id in mentioned_user_ids:
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
