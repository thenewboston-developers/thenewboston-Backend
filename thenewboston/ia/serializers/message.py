from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Conversation, Message
from ..models.message import SenderType


class MessageReadSerializer(serializers.ModelSerializer):
    conversation = serializers.PrimaryKeyRelatedField(queryset=Conversation.objects.all())
    sender = UserReadSerializer(read_only=True)

    class Meta:
        model = Message
        fields = '__all__'


class MessageWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Message
        fields = (
            'conversation',
            'text',
        )
        read_only_fields = (
            'created_date',
            'modified_date',
            'sender',
            'sender_type',
        )

    def create(self, validated_data):
        request = self.context.get('request')

        message = super().create({
            **validated_data,
            'sender': request.user,
            'sender_type': SenderType.USER,
        })

        return message

    def validate_conversation(self, conversation):
        user = self.context['request'].user

        if conversation.owner != user:
            raise serializers.ValidationError('You are not the owner of this conversation.')

        return conversation
