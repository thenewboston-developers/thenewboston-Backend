from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectSenderOrReadOnly

from ..models import Message
from ..serializers.message import MessageReadSerializer, MessageWriteSerializer


class MessageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectSenderOrReadOnly]
    queryset = Message.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        read_serializer = MessageReadSerializer(message, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return MessageWriteSerializer

        return MessageReadSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save()
        read_serializer = MessageReadSerializer(conversation, context={'request': request})

        return Response(read_serializer.data)
