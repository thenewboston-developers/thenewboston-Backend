from django.conf import settings
from rest_framework import serializers

from thenewboston.general.constants import OPENAI_IMAGE_CREATION_FEE
from thenewboston.wallets.utils.wallet import get_default_wallet


class OpenAIImageSerializer(serializers.Serializer):
    description = serializers.CharField(required=True, max_length=1000)
    quantity = serializers.IntegerField(required=True, min_value=1, max_value=10)

    def validate_quantity(self, value):

        user = self.context.get('user')
        wallet = get_default_wallet(user)
        if not wallet:
            raise serializers.ValidationError(f'Core {settings.DEFAULT_CORE_TICKER} wallet not found.')

        total_image_creation_fee = OPENAI_IMAGE_CREATION_FEE * value
        if total_image_creation_fee > wallet.balance:
            raise serializers.ValidationError(
                f'Insufficient balance. Total artwork creation fee: {total_image_creation_fee}, '
                f'Wallet balance: {wallet.balance}'
            )

        return value
