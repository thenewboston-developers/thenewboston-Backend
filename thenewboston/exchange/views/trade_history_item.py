from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import ListModelMixin
from rest_framework.viewsets import GenericViewSet

from thenewboston.general.pagination import CustomPageNumberPagination

from ..serializers.trade_history_item import TradeHistoryItemSerializer


class RequiredOrderingFilter(OrderingFilter):

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)

        if not ordering:
            raise ValidationError(
                'Ordering parameter is required. Please provide both field and direction '
                '(e.g., ?ordering=price or ?ordering=-price)'
            )

        return queryset.order_by(*ordering)


class TradeHistoryItemViewSet(ListModelMixin, GenericViewSet):
    filter_backends = [RequiredOrderingFilter]
    ordering_fields = [
        'asset_pair__primary_currency__ticker', 'change_1h', 'change_24h', 'change_7d', 'market_cap', 'price',
        'volume_24h'
    ]
    pagination_class = CustomPageNumberPagination
    queryset = TradeHistoryItemSerializer.Meta.model.objects.select_related(
        'asset_pair', 'asset_pair__primary_currency', 'asset_pair__secondary_currency'
    ).all()
    serializer_class = TradeHistoryItemSerializer
