from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Conversation
from ..serializers.conversation import ConversationReadSerializer, ConversationWriteSerializer


class ConversationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Conversation.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save()
        read_serializer = ConversationReadSerializer(conversation, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        return Conversation.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return ConversationWriteSerializer

        return ConversationReadSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save()
        read_serializer = ConversationReadSerializer(conversation, context={'request': request})

        return Response(read_serializer.data)
