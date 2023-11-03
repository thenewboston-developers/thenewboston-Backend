import uuid

import requests
from django.core.files.base import ContentFile
from rest_framework import serializers

from thenewboston.cores.models import Core
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Artwork


class ArtworkReadSerializer(serializers.ModelSerializer):
    creator = UserReadSerializer(read_only=True)
    owner = UserReadSerializer(read_only=True)

    class Meta:
        model = Artwork
        fields = '__all__'


class ArtworkWriteSerializer(serializers.ModelSerializer):
    image_url = serializers.URLField(write_only=True)
    price_core = serializers.PrimaryKeyRelatedField(queryset=Core.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Artwork
        fields = ('description', 'image_url', 'name', 'price_amount', 'price_core')
        read_only_fields = (
            'created_date',
            'creator',
            'modified_date',
            'owner',
        )

    def create(self, validated_data):
        request = self.context.get('request')
        image_url = validated_data.pop('image_url')
        response = requests.get(image_url)
        image = ContentFile(response.content, f'{uuid.uuid4()}.png')
        artwork = Artwork.objects.create(creator=request.user, image=image, owner=request.user, **validated_data)

        return artwork
