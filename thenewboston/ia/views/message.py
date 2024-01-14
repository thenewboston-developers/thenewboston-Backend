from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from openai import OpenAI
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectSenderOrReadOnly
from thenewboston.ia.utils.ia import get_ia

from ..filters.message import MessageFilter
from ..models import Message
from ..models.message import SenderType
from ..serializers.message import MessageReadSerializer, MessageWriteSerializer


class MessageViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = MessageFilter
    permission_classes = [IsAuthenticated, IsObjectSenderOrReadOnly]
    queryset = Message.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        read_serializer = MessageReadSerializer(message, context={'request': request})

        Message.objects.create(
            conversation=message.conversation,
            sender=get_ia(),
            sender_type=SenderType.IA,
            text=self.generate_ias_response(message.conversation)
        )

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def generate_ias_response(self, conversation):
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        messages = self.get_messages(conversation)
        response = client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=messages,
        )
        response_dict = response.dict()
        return response_dict['choices'][0]['message']['content']

    @staticmethod
    def get_messages(conversation):
        messages = Message.objects.filter(conversation=conversation).order_by('created_date')
        results = [
            {
                'role': 'system',
                'content': 'Your name is Ia. Your job is to ask the user questions to get to know them.'
            },
        ]

        for message in messages:
            if message.sender_type == SenderType.IA:
                results.append({'role': 'assistant', 'content': message.text})
            elif message.sender_type == SenderType.USER:
                results.append({'role': 'user', 'content': message.text})

        return results

    def get_queryset(self):
        return Message.objects.filter(conversation__owner=self.request.user)

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
