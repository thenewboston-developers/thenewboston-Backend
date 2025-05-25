from rest_framework import serializers

from ..models import Wire


class WireSerializer(serializers.ModelSerializer):

    class Meta:
        model = Wire
        fields = '__all__'

    def validate_currency(self, value):
        if value and not value.domain:
            raise serializers.ValidationError('Wires are not supported for internal currencies.')
        return value
