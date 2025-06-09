import django_filters

from ..models import Trade


class TradeFilter(django_filters.FilterSet):
    buy_order__primary_currency = django_filters.NumberFilter(field_name='buy_order__primary_currency')
    buy_order__secondary_currency = django_filters.NumberFilter(field_name='buy_order__secondary_currency')

    class Meta:
        model = Trade
        fields = {
            'buy_order': ['exact'],
            'sell_order': ['exact'],
            'buy_order__primary_currency': ['exact'],
            'buy_order__secondary_currency': ['exact'],
        }
