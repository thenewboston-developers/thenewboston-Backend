import django_filters

from ..models import Trade


class TradeFilter(django_filters.FilterSet):
    buy_order__asset_pair = django_filters.NumberFilter(field_name='buy_order__asset_pair')

    class Meta:
        model = Trade
        fields = {
            # TODO(dmu) LOW: Are these definitions excessive?
            'buy_order': ['exact'],
            'sell_order': ['exact'],
            'buy_order__asset_pair': ['exact'],
        }
