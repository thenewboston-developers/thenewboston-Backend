from django.db.models import Sum
from rest_framework import serializers

from ..models import Currency


class TotalAmountMintedSerializer(serializers.ModelSerializer):
    total_amount_minted = serializers.SerializerMethodField()

    class Meta:
        model = Currency
        fields = ('id', 'ticker', 'total_amount_minted')

    @staticmethod
    def get_total_amount_minted(obj):
        return obj.mints.aggregate(total=Sum('amount'))['total'] or 0
