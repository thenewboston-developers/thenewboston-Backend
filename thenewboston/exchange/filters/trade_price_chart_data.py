from datetime import timedelta

import django_filters
from django.utils import timezone

from thenewboston.exchange.models import AssetPair, Trade


class TradePriceChartDataFilter(django_filters.FilterSet):
    asset_pair = django_filters.NumberFilter(method='filter_asset_pair', required=True)
    time_range = django_filters.ChoiceFilter(
        method='filter_time_range',
        choices=[
            ('1d', '1 Day'),
            ('1w', '1 Week'),
            ('1m', '1 Month'),
            ('3m', '3 Months'),
            ('1y', '1 Year'),
            ('all', 'All Time'),
        ],
        required=True
    )

    class Meta:
        model = Trade
        fields = ('asset_pair', 'time_range')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.asset_pair_obj = None
        self.start_time = None
        self.time_range_value = None

    def filter_asset_pair(self, queryset, name, value):
        try:
            asset_pair = AssetPair.objects.get(pk=value)
            self.asset_pair_obj = asset_pair
            return queryset.filter(
                buy_order__primary_currency=asset_pair.primary_currency,
                buy_order__secondary_currency=asset_pair.secondary_currency
            )
        except AssetPair.DoesNotExist:
            self.asset_pair_obj = None
            return queryset.none()

    def filter_time_range(self, queryset, name, value):
        now = timezone.now()
        time_ranges = {
            '1d': now - timedelta(days=1),
            '1w': now - timedelta(days=7),
            '1m': now - timedelta(days=30),
            '3m': now - timedelta(days=90),
            '1y': now - timedelta(days=365),
            'all': None,
        }

        start_time = time_ranges.get(value)
        self.start_time = start_time
        self.time_range_value = value

        if start_time:
            return queryset.filter(created_date__gte=start_time)

        return queryset
