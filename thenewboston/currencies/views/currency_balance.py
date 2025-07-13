from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value, Window
from django.db.models.functions import Cast, Rank
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.wallets.models import Wallet

from ..filters.currency_balance import CurrencyBalanceFilter
from ..models import Mint
from ..serializers.currency_balance import CurrencyBalanceSerializer


class CurrencyBalanceListView(generics.ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = CurrencyBalanceFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated]
    serializer_class = CurrencyBalanceSerializer

    def get_queryset(self):
        currency_id = self.request.GET.get('currency')
        queryset = Wallet.objects.filter(balance__gt=0, currency_id=currency_id).select_related('owner', 'currency')
        total_minted = Mint.objects.filter(currency_id=currency_id).aggregate(total=Sum('amount'))['total'] or 0

        if total_minted > 0:
            queryset = queryset.annotate(
                rank=Window(expression=Rank(), order_by=F('balance').desc()),
                percentage=ExpressionWrapper(
                    Cast(F('balance'), DecimalField(max_digits=20, decimal_places=4)) * 100.0 / total_minted,
                    output_field=DecimalField(max_digits=10, decimal_places=4)
                )
            )
        else:
            queryset = queryset.annotate(
                rank=Window(expression=Rank(), order_by=F('balance').desc()),
                percentage=Value(0, output_field=DecimalField(max_digits=10, decimal_places=4))
            )

        return queryset.order_by('-balance')
