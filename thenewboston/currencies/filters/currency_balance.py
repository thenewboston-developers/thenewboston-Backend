import django_filters

from thenewboston.wallets.models import Wallet


class CurrencyBalanceFilter(django_filters.FilterSet):
    currency = django_filters.NumberFilter(field_name='currency', required=True)

    class Meta:
        model = Wallet
        fields = ('currency',)
