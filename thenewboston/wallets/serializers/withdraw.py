from rest_framework import serializers

from thenewboston.general.constants import ACCOUNT_NUMBER_LENGTH, TRANSACTION_FEE
from thenewboston.general.validators import HexStringValidator


class WithdrawSerializer(serializers.Serializer):
    account_number = serializers.CharField(validators=[HexStringValidator(ACCOUNT_NUMBER_LENGTH)])
    amount = serializers.IntegerField(min_value=TRANSACTION_FEE + 1)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass

    def validate(self, data):
        wallet = self.context['wallet']

        if data['amount'] > wallet.balance:
            raise serializers.ValidationError('Insufficient funds in the wallet.')

        # Check if currency is internal
        if not wallet.currency.domain:
            raise serializers.ValidationError('Withdrawals are not supported for internal currencies.')

        return data
