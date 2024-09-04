from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.enums import MessageType
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly
from thenewboston.notifications.consumers.notification import NotificationConsumer
from thenewboston.notifications.models.notification import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Comment
from ..serializers.comment import CommentReadSerializer, CommentUpdateSerializer, CommentWriteSerializer


class CommentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Comment.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        read_serializer = CommentReadSerializer(comment, context={'request': request})

        if comment.post.owner != comment.owner:
            self.notify_post_owner(comment=comment)

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def notify_post_owner(self, comment):
        post = comment.post
        notification = Notification.objects.create(
            owner=post.owner,
            payload={
                'post_id': post.id,
                'commenter': UserReadSerializer(comment.owner).data,
                'comment': comment.content,
                'notification_type': 'POST_COMMENT',
            }
        )

        notification_data = NotificationReadSerializer(notification).data

        NotificationConsumer.stream_notification(
            message_type=MessageType.CREATE_NOTIFICATION, notification_data=notification_data
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return CommentWriteSerializer

        if self.action in ['partial_update', 'update']:
            return CommentUpdateSerializer

        return CommentReadSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        read_serializer = CommentReadSerializer(comment, context={'request': request})

        return Response(read_serializer.data)
