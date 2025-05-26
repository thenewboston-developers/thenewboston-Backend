from django.contrib.auth import get_user_model
from rest_framework import exceptions, serializers

from ..models import Currency

User = get_user_model()


class CurrencyReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = Currency
        fields = '__all__'


class CurrencyWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Currency
        fields = '__all__'
        read_only_fields = (
            'created_date',
            'modified_date',
            'owner',
            'currency_type',
        )

    def create(self, validated_data):
        request = self.context.get('request')

        if not request.user.is_staff:
            # TODO(dmu) MEDIUM: Use `permission_classes` for checking permissions
            raise exceptions.PermissionDenied('You do not have permission to create a Currency.')

        domain = validated_data.get('domain')
        validated_data['currency_type'] = 'external' if domain else 'internal'

        currency = super().create({
            **validated_data,
            'owner': request.user,
        })

        return currency
