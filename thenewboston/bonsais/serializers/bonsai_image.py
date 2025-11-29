from rest_framework import serializers

from ..models import BonsaiImage


class BonsaiImageSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    order = serializers.IntegerField(required=False)
    image = serializers.ImageField(required=False, allow_null=True, write_only=True)
    url = serializers.ImageField(read_only=True, source='image')

    class Meta:
        model = BonsaiImage
        fields = ('id', 'image', 'order', 'url')
        read_only_fields = ('url',)
