from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.wallets.models import Wallet

from ..serializers.currency_balance import CurrencyBalanceSerializer


class CurrencyBalanceListView(generics.ListAPIView):
    serializer_class = CurrencyBalanceSerializer
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        currency_id = self.request.query_params.get('currency__id')

        if not currency_id:
            raise ValidationError({'currency__id': 'This query parameter is required.'})

        return Wallet.objects.filter(currency_id=currency_id,
                                     balance__gt=0).select_related('owner', 'currency').order_by('-balance')
