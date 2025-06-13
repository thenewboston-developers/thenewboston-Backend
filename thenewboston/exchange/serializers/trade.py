from rest_framework import serializers

from ..models import Trade


class TradeSerializer(serializers.ModelSerializer):
    primary_currency = serializers.IntegerField(source='buy_order.primary_currency_id', read_only=True)
    secondary_currency = serializers.IntegerField(source='buy_order.secondary_currency_id', read_only=True)

    class Meta:
        model = Trade
        fields = '__all__'
