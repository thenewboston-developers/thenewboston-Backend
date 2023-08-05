from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Comment


class CommentReadSerializer(serializers.ModelSerializer):
    owner = UserReadSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = (
            'content',
            'created_date',
            'id',
            'modified_date',
            'owner',
            'post',
        )
        read_only_fields = (
            'content',
            'created_date',
            'id',
            'modified_date',
            'owner',
            'post',
        )


class CommentWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Comment
        fields = ('content', 'post')

    def create(self, validated_data):
        request = self.context.get('request')
        post = super().create({
            **validated_data,
            'owner': request.user,
        })
        return post
