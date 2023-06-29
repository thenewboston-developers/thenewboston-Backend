import django_filters

from ..models import Trade


class TradeFilter(django_filters.FilterSet):

    class Meta:
        model = Trade
        fields = ('buy_order', 'sell_order')
