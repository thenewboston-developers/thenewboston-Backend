from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from thenewboston.general.constants import MAX_MINT_AMOUNT
from thenewboston.general.utils.transfers import change_wallet_balance
from thenewboston.wallets.models import Wallet

from ..models import Mint


class MintSerializer(serializers.ModelSerializer):

    class Meta:
        model = Mint
        fields = ('id', 'currency', 'amount', 'created_date', 'modified_date')
        read_only_fields = ('id', 'currency', 'created_date', 'modified_date')

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get('request')
        currency = self.context.get('currency')
        amount = validated_data.get('amount')

        # Check if user owns the currency
        if currency.owner != request.user:
            raise serializers.ValidationError('You do not own this currency.')

        # Check if currency is internal
        if currency.domain:
            raise serializers.ValidationError('Cannot mint external currencies.')

        # Check total minted amount
        total_minted = Mint.objects.filter(currency=currency).aggregate(total=Sum('amount'))['total'] or 0

        if total_minted + amount > MAX_MINT_AMOUNT:
            raise serializers.ValidationError(
                f'Total minted amount would exceed maximum of {MAX_MINT_AMOUNT:,}. '
                f'Current total: {total_minted:,}'
            )

        # Create mint record
        mint = super().create({
            **validated_data,
            'currency': currency,
            'owner': request.user,
        })

        # Get or create wallet and add minted coins
        wallet, _ = Wallet.objects.select_for_update().get_or_create(
            owner=request.user, currency=currency, defaults={'balance': 0}
        )

        change_wallet_balance(wallet, amount)

        return mint

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Amount must be greater than 0.')

        if value > MAX_MINT_AMOUNT:
            raise serializers.ValidationError(f'Amount cannot exceed {MAX_MINT_AMOUNT:,}.')

        return value
