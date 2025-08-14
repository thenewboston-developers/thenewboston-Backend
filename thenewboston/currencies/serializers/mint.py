from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from thenewboston.general.constants import MAX_MINT_AMOUNT
from thenewboston.wallets.models import Wallet

from ..models import Currency, Mint


class MintReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mint
        fields = '__all__'


class MintWriteSerializer(serializers.ModelSerializer):
    currency = serializers.PrimaryKeyRelatedField(queryset=Currency.objects.all())

    class Meta:
        model = Mint
        fields = ('currency', 'amount')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        currency = validated_data.get('currency')
        amount = validated_data.get('amount')

        if currency.owner != request.user:
            raise serializers.ValidationError('You do not own this currency.')

        if currency.domain:
            raise serializers.ValidationError('Cannot mint external currencies.')

        total_minted = Mint.objects.filter(currency=currency).aggregate(total=Sum('amount'))['total'] or 0
        if total_minted + amount > MAX_MINT_AMOUNT:
            raise serializers.ValidationError(
                f'Total minted amount would exceed maximum of {MAX_MINT_AMOUNT:,}. Current total: {total_minted:,}'
            )

        mint = super().create({**validated_data, 'owner': request.user})
        wallet, _ = Wallet.objects.select_for_update().get_or_create(
            owner=request.user, currency=currency, defaults={'balance': 0}
        )
        wallet.change_balance(amount)
        return mint

    @staticmethod
    def validate_amount(value):
        if value <= 0:
            raise serializers.ValidationError('Amount must be greater than 0.')

        if value > MAX_MINT_AMOUNT:
            raise serializers.ValidationError(f'Amount cannot exceed {MAX_MINT_AMOUNT:,}.')

        return value
