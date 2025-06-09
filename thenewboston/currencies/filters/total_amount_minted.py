import django_filters

from ..models import Currency


class TotalAmountMintedFilter(django_filters.FilterSet):
    currency = django_filters.NumberFilter(field_name='id', required=True)

    class Meta:
        model = Currency
        fields = ('currency',)
