from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Notification
from ..serializers.notification import NotificationReadSerializer, NotificationUpdateSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Notification.objects.all()

    def get_queryset(self):
        return Notification.objects.filter(owner=self.request.user).order_by('-created_date')

    def get_serializer_class(self):
        if self.action in ['partial_update', 'update']:
            return NotificationUpdateSerializer

        return NotificationReadSerializer

    def list(self, request, *args, **kwargs):  # noqa: A003
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            unread_count = self.get_queryset().filter(is_read=False).count()
            response.data['unread_count'] = unread_count
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        notification = serializer.save()
        read_serializer = NotificationReadSerializer(notification)

        return Response(read_serializer.data)

    @action(detail=False, methods=['patch'], url_path='mark-all-as-read')
    def mark_all_as_read(self, request):
        notifications = self.get_queryset().filter(is_read=False)
        notifications.update(is_read=True)
        return Response({'success': True, 'unread_count': 0})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        unread_count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': unread_count})
