from rest_framework import serializers


class OpenAIImageSerializer(serializers.Serializer):
    description = serializers.CharField(required=True, max_length=1000)
