from rest_framework.mixins import ListModelMixin
from rest_framework.viewsets import GenericViewSet

from thenewboston.general.pagination import CustomPageNumberPagination

from ..serializers.trade_history_item import TradeHistoryItemSerializer


class TradeHistoryItemViewSet(ListModelMixin, GenericViewSet):
    serializer_class = TradeHistoryItemSerializer
    queryset = TradeHistoryItemSerializer.Meta.model.objects.select_related(
        'asset_pair', 'asset_pair__primary_currency', 'asset_pair__secondary_currency'
    ).order_by('asset_pair__primary_currency__ticker', 'asset_pair__secondary_currency__ticker').all()
    pagination_class = CustomPageNumberPagination
    # TODO(dmu) MEDIUM: Add filtering to retrieve trending, top and new currencies.
    #                   Add an attribute on currency to filter by
