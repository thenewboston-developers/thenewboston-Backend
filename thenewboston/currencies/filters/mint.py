import django_filters

from ..models import Mint


class MintFilter(django_filters.FilterSet):
    currency = django_filters.NumberFilter(field_name='currency', required=True)

    class Meta:
        model = Mint
        fields = ('currency',)
