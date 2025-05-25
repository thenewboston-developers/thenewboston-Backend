from django.contrib.auth import get_user_model
from rest_framework import exceptions, serializers

from thenewboston.general.utils.image import process_image, validate_image_dimensions

from ..models import Currency

User = get_user_model()


class CurrencyReadSerializer(serializers.ModelSerializer):

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

    def validate_logo(self, value):
        """Validate that the logo is exactly 512x512 pixels."""
        is_valid, error_message = validate_image_dimensions(value, 512, 512)
        if not is_valid:
            raise serializers.ValidationError(error_message)

        # Reset file position to beginning after validation since Image.open() moves it to the end
        value.seek(0)
        return value

    def create(self, validated_data):
        request = self.context.get('request')

        if not request.user.is_staff:
            # TODO(dmu) MEDIUM: Use `permission_classes` for checking permissions
            raise exceptions.PermissionDenied('You do not have permission to create a Currency.')

        # Process the logo image
        logo = validated_data.get('logo')
        if logo:
            validated_data['logo'] = process_image(logo)

        currency = super().create({
            **validated_data,
            'owner': request.user,
        })

        return currency

    def update(self, instance, validated_data):
        """Update the Currency instance."""
        logo = validated_data.get('logo')
        if logo:
            validated_data['logo'] = process_image(logo)

        return super().update(instance, validated_data)
