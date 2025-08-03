import django_filters

from ..models import AssetPair


class AssetPairFilter(django_filters.FilterSet):
    primary_currency_ticker = django_filters.CharFilter(field_name='primary_currency__ticker', lookup_expr='iexact')
    secondary_currency_ticker = django_filters.CharFilter(
        field_name='secondary_currency__ticker', lookup_expr='iexact'
    )

    class Meta:
        model = AssetPair
        fields = ['primary_currency_ticker', 'secondary_currency_ticker']
