from rest_framework import serializers

from ..models import Trade


class TradeSerializer(serializers.ModelSerializer):
    asset_pair = serializers.IntegerField(source='buy_order.asset_pair_id', read_only=True)

    class Meta:
        model = Trade
        fields = '__all__'
