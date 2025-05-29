from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from thenewboston.exchange.models import AssetPair
from thenewboston.general.utils.image import process_image, validate_image_dimensions
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Currency
from ..utils.currency import get_default_currency

User = get_user_model()


class CurrencyReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = Currency
        fields = '__all__'


class CurrencyReadDetailSerializer(serializers.ModelSerializer):
    owner = UserReadSerializer(read_only=True)

    class Meta:
        model = Currency
        fields = '__all__'


class CurrencyWriteSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(required=True)

    class Meta:
        model = Currency
        fields = '__all__'
        read_only_fields = (
            'created_date',
            'modified_date',
            'owner',
        )

    def create(self, validated_data):
        request = self.context.get('request')

        if logo := validated_data.get('logo'):
            validated_data['logo'] = process_image(logo)

        with transaction.atomic():
            currency = super().create({
                **validated_data,
                'owner': request.user,
            })
            default_currency = get_default_currency()
            AssetPair.objects.create(primary_currency=currency, secondary_currency=default_currency)

        return currency

    def update(self, instance, validated_data):
        if logo := validated_data.get('logo'):
            validated_data['logo'] = process_image(logo)

        return super().update(instance, validated_data)

    def validate_domain(self, value):
        request = self.context.get('request')

        if value and not request.user.is_staff:
            raise serializers.ValidationError('Only staff users can create external currencies (with domains).')

        return value

    @staticmethod
    def validate_logo(value):
        is_valid, error_message = validate_image_dimensions(value, 512, 512)
        if not is_valid:
            raise serializers.ValidationError(error_message)

        # Reset file position to the beginning after validation since Image.open() moves it to the end
        value.seek(0)
        return value
