from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import PostReaction


class PostReactionsReadSerializer(serializers.ModelSerializer):
    user = UserReadSerializer(read_only=True)

    class Meta:
        model = PostReaction
        fields = ('reaction', 'user')
        read_only_fields = (
            'user',
            'reaction',
        )
