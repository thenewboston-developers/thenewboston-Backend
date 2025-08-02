from rest_framework import serializers

from thenewboston.currencies.serializers.currency import CurrencyReadSerializer, CurrencyTinySerializer

from ..models import AssetPair


class AssetPairSerializer(serializers.ModelSerializer):
    primary_currency = CurrencyReadSerializer(read_only=True)
    secondary_currency = CurrencyReadSerializer(read_only=True)

    class Meta:
        model = AssetPair
        fields = '__all__'


class AssetPairTinySerializer(serializers.ModelSerializer):
    primary_currency = CurrencyTinySerializer(read_only=True)
    secondary_currency = CurrencyTinySerializer(read_only=True)

    class Meta:
        model = AssetPair
        fields = '__all__'
