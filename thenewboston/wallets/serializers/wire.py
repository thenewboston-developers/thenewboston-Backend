from rest_framework import serializers

from ..models import Wire


class WireSerializer(serializers.ModelSerializer):

    class Meta:
        model = Wire
        fields = '__all__'
