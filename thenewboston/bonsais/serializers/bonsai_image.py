from rest_framework import serializers

from ..models import BonsaiImage


class BonsaiImageSerializer(serializers.ModelSerializer):
    order = serializers.IntegerField(required=False)

    class Meta:
        model = BonsaiImage
        fields = ('id', 'url', 'order')
        read_only_fields = ('id',)
