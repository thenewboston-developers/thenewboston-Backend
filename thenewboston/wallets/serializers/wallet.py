from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from thenewboston.cores.serializers.core import CoreReadSerializer
from thenewboston.general.utils.cryptography import generate_key_pair

from ..models import Wallet


class WalletReadSerializer(serializers.ModelSerializer):
    core = CoreReadSerializer(read_only=True)

    class Meta:
        model = Wallet
        fields = (
            'balance',
            'core',
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
        fields = ('id', 'core', 'balance')
        read_only_fields = ('balance',)

    def create(self, validated_data):
        request = self.context.get('request')
        key_pair = generate_key_pair()

        wallet = super().create({
            **validated_data,
            'owner': request.user,
            'deposit_account_number': key_pair.public,
            'deposit_signing_key': key_pair.private,
        })

        return wallet

    def validate(self, data):
        request = self.context.get('request')
        owner = request.user
        core = data['core']

        if Wallet.objects.filter(owner=owner, core=core).exists():
            raise ValidationError('A wallet with this owner and core already exists.')

        return data
