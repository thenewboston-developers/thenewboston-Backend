from rest_framework import serializers


class ChartDataPointSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField()
    price = serializers.IntegerField()
    volume = serializers.IntegerField()
    open = serializers.IntegerField()  # noqa: A003
    high = serializers.IntegerField()
    low = serializers.IntegerField()


class ChartDataResponseSerializer(serializers.Serializer):
    data = ChartDataPointSerializer(many=True)
    interval_minutes = serializers.IntegerField()
    total_points = serializers.IntegerField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
