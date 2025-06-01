from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet


class CurrencyBalanceSerializer(serializers.ModelSerializer):
    owner = UserReadSerializer(read_only=True)

    class Meta:
        model = Wallet
        fields = ('owner', 'balance')
