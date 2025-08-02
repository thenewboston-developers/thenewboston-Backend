from rest_framework import serializers

from ..models import Trade


class TradeSerializer(serializers.ModelSerializer):
    asset_pair = serializers.IntegerField(source='buy_order.asset_pair_id', read_only=True)

    # TODO(dmu) MEDIUM: Consider removal of `primary_currency` and `secondary_currency` in favor of `asset_pair`
    primary_currency = serializers.IntegerField(source='buy_order.asset_pair.primary_currency_id', read_only=True)
    secondary_currency = serializers.IntegerField(source='buy_order.asset_pair.secondary_currency_id', read_only=True)

    class Meta:
        model = Trade
        fields = '__all__'
