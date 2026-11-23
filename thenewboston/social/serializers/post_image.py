from rest_framework import serializers

from thenewboston.general.utils.image import process_image

from ..constants import MAX_UNATTACHED_POST_IMAGES_PER_USER
from ..models import PostImage


class PostImageReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostImage
        fields = ('id', 'image')
        read_only_fields = fields


class PostImageWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostImage
        fields = ('image',)

    def create(self, validated_data):
        request = self.context.get('request')
        return super().create({'image': process_image(validated_data['image']), 'owner': request.user})

    def validate(self, data):
        user = self.context['request'].user
        unattached_count = PostImage.objects.filter(owner=user, post__isnull=True).count()

        if unattached_count >= MAX_UNATTACHED_POST_IMAGES_PER_USER:
            raise serializers.ValidationError('You have too many images that are not part of a post. Try again later.')

        return data
