from rest_framework import serializers

from thenewboston.currencies.serializers.currency import CurrencyReadSerializer

from ..models import Wallet


class UserWalletSerializer(serializers.ModelSerializer):
    currency = CurrencyReadSerializer(read_only=True)
    rank = serializers.IntegerField(read_only=True)
    total_users = serializers.IntegerField(read_only=True)
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = (
            'id',
            'currency',
            'balance',
            'rank',
            'total_users',
            'is_owner',
            'created_date',
            'modified_date',
        )

    @staticmethod
    def get_is_owner(obj):
        return obj.currency.owner_id == obj.owner_id
