from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import PostLike


class PostLikeReadSerializer(serializers.ModelSerializer):
    user = UserReadSerializer(read_only=True)

    class Meta:
        model = PostLike
        fields = ('id', 'user', 'created_date')
        read_only_fields = fields


class PostLikeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostLike
        fields = ('post',)

    def create(self, validated_data):
        request = self.context.get('request')
        return super().create(
            {
                **validated_data,
                'user': request.user,
            }
        )
