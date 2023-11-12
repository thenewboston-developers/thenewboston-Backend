import django_filters

from ..models import Trade


class TradeFilter(django_filters.FilterSet):
    buy_order__primary_currency__id = django_filters.NumberFilter(field_name='buy_order__primary_currency__id')
    buy_order__secondary_currency__id = django_filters.NumberFilter(field_name='buy_order__secondary_currency__id')

    class Meta:
        model = Trade
        fields = {
            'buy_order': ['exact'],
            'sell_order': ['exact'],
            'buy_order__primary_currency__id': ['exact'],
            'buy_order__secondary_currency__id': ['exact'],
        }
