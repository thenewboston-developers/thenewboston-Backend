from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from thenewboston.currencies.serializers.currency import CurrencyReadSerializer
from thenewboston.general.utils.cryptography import generate_key_pair

from ..models import Wallet


class WalletReadSerializer(serializers.ModelSerializer):
    currency = CurrencyReadSerializer(read_only=True)

    class Meta:
        model = Wallet
        fields = (
            'balance',
            'currency',
            'created_date',
            'deposit_account_number',
            'deposit_balance',
            'id',
            'modified_date',
            'owner',
        )


class WalletWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ('id', 'currency', 'balance')
        read_only_fields = ('balance',)

    def create(self, validated_data):
        request = self.context.get('request')
        key_pair = generate_key_pair()

        wallet = super().create(
            {
                **validated_data,
                'owner': request.user,
                'deposit_account_number': key_pair.public,
                'deposit_signing_key': key_pair.private,
            }
        )

        return wallet

    def validate(self, data):
        request = self.context.get('request')
        owner = request.user
        currency = data['currency']

        if Wallet.objects.filter(owner=owner, currency=currency).exists():
            raise ValidationError('A wallet with this owner and currency already exists.')

        return data
