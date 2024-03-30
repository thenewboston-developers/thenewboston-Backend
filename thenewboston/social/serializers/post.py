import uuid
from pathlib import Path

from django.core.files.base import ContentFile
from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Post
from ..serializers.comment import CommentReadSerializer


class PostReadSerializer(serializers.ModelSerializer):
    comments = CommentReadSerializer(many=True, read_only=True)
    owner = UserReadSerializer(read_only=True)

    class Meta:
        model = Post
        fields = (
            'comments',
            'content',
            'created_date',
            'id',
            'image',
            'modified_date',
            'owner',
        )
        read_only_fields = (
            'comments',
            'content',
            'created_date',
            'id',
            'image',
            'modified_date',
            'owner',
        )


class PostWriteSerializer(serializers.ModelSerializer):

    is_image_cleared = serializers.BooleanField(
        default=False,
        write_only=True,
        required=False,
        help_text='A boolean flag indicating whether the existing image should be cleared.'
    )

    class Meta:
        model = Post
        fields = ('content', 'image', 'is_image_cleared')

    def create(self, validated_data):
        request = self.context.get('request')
        image = validated_data.get('image')

        # Removing is_image_cleared from validated_data since it's not part of the Post model
        validated_data.pop('is_image_cleared', None)

        if image:
            extension = Path(image.name).suffix
            filename = f'{uuid.uuid4()}{extension}'
            file = ContentFile(image.read(), filename)
            validated_data['image'] = file

        post = super().create({
            **validated_data,
            'owner': request.user,
        })
        return post

    def update(self, instance, validated_data):
        """
        Update the Post instance.

        This method updates the content and image of a Post instance. If a new image is provided,
        it replaces the existing image. If 'is_image_cleared' is True, it removes the current image.
        Otherwise, it leaves the image unchanged.
        """
        image = validated_data.get('image')
        instance.content = validated_data.get('content', instance.content)
        if image:
            extension = Path(image.name).suffix
            filename = f'{uuid.uuid4()}{extension}'
            file = ContentFile(image.read(), filename)
            instance.image = file
        elif validated_data.get('is_image_cleared'):
            instance.image = None

        instance.save()
        return instance
