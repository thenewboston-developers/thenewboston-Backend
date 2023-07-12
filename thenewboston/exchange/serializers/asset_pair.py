from rest_framework import serializers

from thenewboston.cores.serializers.core import CoreReadSerializer

from ..models import AssetPair


class AssetPairSerializer(serializers.ModelSerializer):
    primary_currency = CoreReadSerializer(read_only=True)
    secondary_currency = CoreReadSerializer(read_only=True)

    class Meta:
        model = AssetPair
        fields = '__all__'
