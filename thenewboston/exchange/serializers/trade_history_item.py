from rest_framework import serializers

from thenewboston.currencies.models import Currency

from ..models import TradeHistoryItem


class CurrencyTinySerializer(serializers.ModelSerializer):

    class Meta:
        model = Currency
        fields = ('id', 'logo', 'ticker')


class TradeHistoryItemSerializer(serializers.ModelSerializer):
    primary_currency = CurrencyTinySerializer(read_only=True)
    secondary_currency = CurrencyTinySerializer(read_only=True)

    class Meta:
        model = TradeHistoryItem
        # TODO(dmu) LOW: Read fields from model metadata instead and remove unnecessary
        fields = (
            'primary_currency', 'secondary_currency', 'price', 'change_1h', 'change_24h', 'change_7d', 'volume_24h',
            'market_cap', 'sparkline'
        )
