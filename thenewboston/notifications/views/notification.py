from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Notification
from ..serializers.notification import NotificationReadSerializer, NotificationUpdateSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Notification.objects.all()

    def get_queryset(self):
        return Notification.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.action in ['partial_update', 'update']:
            return NotificationUpdateSerializer

        return NotificationReadSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        notification = serializer.save()
        read_serializer = NotificationReadSerializer(notification)

        return Response(read_serializer.data)

    @action(detail=False, methods=['patch'])
    def mark_all_as_read(self, request):
        notifications = self.get_queryset().filter(is_read=False)
        notifications.update(is_read=True)
        return Response({'detail': 'All notifications marked as read'})
