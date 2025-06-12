import django_filters

from thenewboston.exchange.models import AssetPair, Trade


class ChartDataFilter(django_filters.FilterSet):
    asset_pair = django_filters.NumberFilter(method='filter_asset_pair', required=True)
    time_range = django_filters.ChoiceFilter(
        method='filter_time_range',
        choices=[
            ('1d', '1 Day'),
            ('1w', '1 Week'),
            ('1m', '1 Month'),
            ('3m', '3 Months'),
            ('all', 'All Time'),
        ],
        required=True
    )

    class Meta:
        model = Trade
        fields = ('asset_pair', 'time_range')

    @staticmethod
    def filter_asset_pair(queryset, name, value):
        try:
            asset_pair = AssetPair.objects.get(pk=value)
            return queryset.filter(
                buy_order__primary_currency=asset_pair.primary_currency,
                buy_order__secondary_currency=asset_pair.secondary_currency
            )
        except AssetPair.DoesNotExist:
            return queryset.none()

    @staticmethod
    def filter_time_range(queryset, name, value):
        # This will be handled in the view
        return queryset
