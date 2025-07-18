from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets

from ..filters.trade import TradeFilter
from ..models import Trade
from ..serializers.trade import TradeSerializer


class TradeViewSet(viewsets.ReadOnlyModelViewSet):
    # TODO(dmu) LOW: We are allowing to see other users trades, but not the orders. Maybe we should allow to
    #                see other users orders as well for consistency?
    #                Just add a filter to orders viewset, so FE can get only own orders.
    filter_backends = [DjangoFilterBackend]
    filterset_class = TradeFilter
    queryset = Trade.objects.select_related('buy_order__primary_currency', 'buy_order__secondary_currency').all()
    serializer_class = TradeSerializer
