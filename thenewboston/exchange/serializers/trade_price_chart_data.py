from rest_framework import serializers


class CandlestickSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    close = serializers.IntegerField()
    volume = serializers.IntegerField()
    open = serializers.IntegerField()  # noqa: A003
    high = serializers.IntegerField()
    low = serializers.IntegerField()


class TradePriceChartDataResponseSerializer(serializers.Serializer):
    candlesticks = CandlestickSerializer(many=True)
    interval_minutes = serializers.IntegerField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    primary_currency = serializers.IntegerField()
    secondary_currency = serializers.IntegerField()
