from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.enums import MessageType, NotificationType
from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectFollowerOrReadOnly
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.notifications.models import Notification
from thenewboston.notifications.serializers.notification import NotificationReadSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..filters.follower import FollowerFilter
from ..models import Follower
from ..serializers.follower import FollowerCreateSerializer, FollowerReadSerializer


class FollowerViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = FollowerFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated, IsObjectFollowerOrReadOnly]
    queryset = Follower.objects.all()

    @staticmethod
    def notify_profile_owner(follower, request):
        notification = Notification.objects.create(
            owner=follower.following,
            payload={
                'follower': UserReadSerializer(follower.follower, context={'request': request}).data,
                'notification_type': NotificationType.PROFILE_FOLLOW.value,
            },
        )

        notification_data = NotificationReadSerializer(notification, context={'request': request}).data

        NotificationConsumer.stream_notification(
            message_type=MessageType.CREATE_NOTIFICATION, notification_data=notification_data
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        follower = serializer.save()
        self.notify_profile_owner(follower, request)
        read_serializer = FollowerReadSerializer(follower, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        following_id = kwargs.get('pk')
        follower = request.user
        follower_relationship = Follower.objects.filter(follower=follower, following_id=following_id)
        follower_relationship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_class(self):
        if self.action == 'create':
            return FollowerCreateSerializer

        return FollowerReadSerializer
