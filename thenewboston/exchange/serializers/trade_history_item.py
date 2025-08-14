from rest_framework import serializers

from thenewboston.currencies.models import Currency

from .asset_pair import AssetPairTinySerializer
from ..models import TradeHistoryItem


class AssetPairSerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ('id', 'logo', 'ticker')


class TradeHistoryItemSerializer(serializers.ModelSerializer):
    asset_pair = AssetPairTinySerializer(read_only=True)

    class Meta:
        model = TradeHistoryItem
        # TODO(dmu) LOW: Read fields from model metadata instead and remove unnecessary
        fields = (
            'asset_pair',
            'price',
            'change_1h',
            'change_24h',
            'change_7d',
            'volume_24h',
            'market_cap',
            'sparkline',
        )
