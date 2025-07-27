from rest_framework import serializers

from ..models import Currency


class TotalAmountMintedSerializer(serializers.ModelSerializer):
    total_amount_minted = serializers.SerializerMethodField()

    class Meta:
        model = Currency
        fields = ('id', 'ticker', 'total_amount_minted')

    @staticmethod
    def get_total_amount_minted(obj):
        # TODO(dmu) LOW: Implement `total_amount_minted` property and declare it as read-only field
        return obj.get_total_amount_minted()
