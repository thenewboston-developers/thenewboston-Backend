import django_filters

from ..models import Whitepaper


class WhitepaperFilter(django_filters.FilterSet):
    currency = django_filters.NumberFilter(field_name='currency')

    class Meta:
        model = Whitepaper
        fields = ('currency',)
