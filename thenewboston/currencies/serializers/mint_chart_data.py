from rest_framework import serializers


class MintDataPointSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField()
    amount_minted = serializers.IntegerField()
    cumulative_total = serializers.IntegerField()


class MintChartDataResponseSerializer(serializers.Serializer):
    data_points = MintDataPointSerializer(many=True)
    currency = serializers.IntegerField()
