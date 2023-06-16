from rest_framework import serializers

from ..models.core import Core


class CoreReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = Core
        fields = '__all__'
