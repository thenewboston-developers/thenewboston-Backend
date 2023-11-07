from rest_framework import serializers


class OpenAIImageSerializer(serializers.Serializer):
    description = serializers.CharField(required=True, max_length=1000)
    quantity = serializers.IntegerField(required=True, min_value=1, max_value=10)
