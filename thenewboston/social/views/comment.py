from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly
from thenewboston.general.utils.text import truncate_text
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.notifications.models.notification import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Comment
from ..serializers.comment import CommentReadSerializer, CommentUpdateSerializer, CommentWriteSerializer
from ..utils.mentions import notify_mentioned_users_in_comment


class CommentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Comment.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        read_serializer = CommentReadSerializer(comment, context={'request': request})

        # Send mention notifications after transaction commits so unread counts are accurate
        mentioned_user_ids = getattr(comment, '_mentioned_user_ids', None)
        if mentioned_user_ids:
            transaction.on_commit(
                lambda comment=comment, mentioned_user_ids=mentioned_user_ids: notify_mentioned_users_in_comment(
                    comment=comment, mentioned_user_ids=mentioned_user_ids, request=request
                )
            )

        # Only send comment notification if post owner wasn't mentioned
        # (to avoid duplicate notifications when post owner is mentioned)
        if comment.post.owner != comment.owner:
            post_owner_was_mentioned = comment.mentioned_users.filter(id=comment.post.owner.id).exists()
            if not post_owner_was_mentioned:
                self.notify_post_owner(comment=comment, request=request)

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action == 'create':
            return CommentWriteSerializer

        if self.action in ['partial_update', 'update']:
            return CommentUpdateSerializer

        return CommentReadSerializer

    @staticmethod
    def notify_post_owner(comment, request):
        post = comment.post
        notification = Notification.objects.create(
            owner=post.owner,
            payload={
                'post_id': post.id,
                'commenter': UserReadSerializer(comment.owner, context={'request': request}).data,
                'comment': comment.content,
                'notification_type': NotificationType.POST_COMMENT.value,
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

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        read_serializer = CommentReadSerializer(comment, context={'request': request})

        return Response(read_serializer.data)
