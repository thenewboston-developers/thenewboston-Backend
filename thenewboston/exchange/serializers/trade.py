from rest_framework import serializers

from ..models import Trade


class TradeSerializer(serializers.ModelSerializer):
    primary_currency = serializers.SerializerMethodField()
    secondary_currency = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = '__all__'

    @staticmethod
    def get_primary_currency(obj):
        return obj.buy_order.primary_currency_id

    @staticmethod
    def get_secondary_currency(obj):
        return obj.buy_order.secondary_currency_id
