from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.notifications.models import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..filters.post_like import PostLikeFilter
from ..models import Post, PostLike
from ..serializers.post_like import PostLikeReadSerializer


class PostLikeViewSet(viewsets.ReadOnlyModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = PostLikeFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated]
    queryset = PostLike.objects.select_related('user').order_by('-created_date')
    serializer_class = PostLikeReadSerializer


class PostActionViewSet(GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PostLikeReadSerializer
    queryset = Post.objects.all()

    @action(detail=True, methods=['post'], url_path='like')
    def like(self, request, pk=None):
        post = self.get_object()
        like, created = PostLike.objects.get_or_create(post=post, user=request.user)

        if not created:
            return Response({'detail': 'You have already liked this post.'}, status=status.HTTP_400_BAD_REQUEST)

        if post.owner != request.user:
            self.notify_post_owner(post=post, liker=request.user, request=request)

        serializer = self.get_serializer(like)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @staticmethod
    def notify_post_owner(post, liker, request):
        notification = Notification.objects.create(
            owner=post.owner,
            payload={
                'post_id': post.id,
                'liker': UserReadSerializer(liker, context={
                    'request': request
                }).data,
                'notification_type': NotificationType.POST_LIKE.value,
            }
        )

        notification_data = NotificationReadSerializer(notification, context={'request': request}).data

        NotificationConsumer.stream_notification(
            message_type=MessageType.CREATE_NOTIFICATION, notification_data=notification_data
        )

    @action(detail=True, methods=['post'], url_path='unlike')
    def unlike(self, request, pk=None):
        post = self.get_object()

        try:
            like = PostLike.objects.get(post=post, user=request.user)
            like.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except PostLike.DoesNotExist:
            return Response({'detail': 'You have not liked this post.'}, status=status.HTTP_400_BAD_REQUEST)
