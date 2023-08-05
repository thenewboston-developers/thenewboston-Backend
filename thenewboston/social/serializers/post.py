from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Post


class PostReadSerializer(serializers.ModelSerializer):
    owner = UserReadSerializer(read_only=True)

    class Meta:
        model = Post
        fields = (
            'content',
            'created_date',
            'id',
            'image',
            'modified_date',
            'owner',
        )
        read_only_fields = (
            'content',
            'created_date',
            'id',
            'image',
            'modified_date',
            'owner',
        )


class PostWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Post
        fields = ('content', 'image')

    def create(self, validated_data):
        request = self.context.get('request')
        post = super().create({
            **validated_data,
            'owner': request.user,
        })
        return post
