from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from thenewboston.cores.serializers.core import CoreReadSerializer

from ..models import Wallet


class WalletReadSerializer(serializers.ModelSerializer):
    core = CoreReadSerializer(read_only=True)

    class Meta:
        model = Wallet
        fields = '__all__'


class WalletWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Wallet
        fields = ('id', 'core', 'balance')
        read_only_fields = ('balance',)

    def create(self, validated_data):
        request = self.context.get('request')
        wallet = super().create({
            **validated_data,
            'owner': request.user,
        })
        return wallet

    def validate(self, data):
        request = self.context.get('request')
        owner = request.user
        core = data['core']

        if Wallet.objects.filter(owner=owner, core=core).exists():
            raise ValidationError('A wallet with this owner and core already exists.')

        return data
