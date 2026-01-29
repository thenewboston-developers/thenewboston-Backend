from rest_framework import serializers

from thenewboston.general.serializers import BaseModelSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..constants import CHAT_MESSAGE_MAX_LENGTH
from ..models import ConnectFiveChatMessage


class ConnectFiveChatMessageCreateSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=CHAT_MESSAGE_MAX_LENGTH, trim_whitespace=False)

    def validate_message(self, value):
        trimmed = value.strip()

        if not trimmed:
            raise serializers.ValidationError('Message cannot be empty.')

        if '\n' in value or '\r' in value:
            raise serializers.ValidationError('Message must be a single line.')

        return trimmed


class ConnectFiveChatMessageReadSerializer(BaseModelSerializer):
    sender = UserReadSerializer(read_only=True)

    class Meta:
        model = ConnectFiveChatMessage
        fields = (
            'created_date',
            'id',
            'match',
            'message',
            'modified_date',
            'sender',
        )
