from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Conversation


class ConversationReadSerializer(serializers.ModelSerializer):
    owner = UserReadSerializer(read_only=True)

    class Meta:
        model = Conversation
        fields = '__all__'


class ConversationWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Conversation
        fields = ('name',)
        read_only_fields = (
            'created_date',
            'modified_date',
            'owner',
        )

    def create(self, validated_data):
        request = self.context.get('request')

        conversation = super().create({
            **validated_data,
            'owner': request.user,
        })

        return conversation
