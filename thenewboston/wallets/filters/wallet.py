import django_filters

from ..models import Wallet


class WalletFilter(django_filters.FilterSet):
    currency = django_filters.NumberFilter(field_name='currency')

    class Meta:
        model = Wallet
        fields = ('currency',)
