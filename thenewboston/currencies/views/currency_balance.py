from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.wallets.models import Wallet

from ..filters.currency_balance import CurrencyBalanceFilter
from ..serializers.currency_balance import CurrencyBalanceSerializer


class CurrencyBalanceListView(generics.ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = CurrencyBalanceFilter
    serializer_class = CurrencyBalanceSerializer
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated]
    queryset = Wallet.objects.filter(balance__gt=0).select_related('owner', 'currency').order_by('-balance')
