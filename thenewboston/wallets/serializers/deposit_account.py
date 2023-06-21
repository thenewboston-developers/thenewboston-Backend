from rest_framework import serializers

from thenewboston.wallets.models.deposit_account import DepositAccount


class DepositAccountSerializer(serializers.Serializer):
    account_number = serializers.SerializerMethodField()

    def create(self, validated_data):
        pass

    @staticmethod
    def get_account_number(user):
        deposit_account = DepositAccount.objects.get(user=user)
        return str(deposit_account.account_number)

    def update(self, instance, validated_data):
        pass
