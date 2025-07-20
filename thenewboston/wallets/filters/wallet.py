import django_filters

from ..models import Wallet


class WalletFilter(django_filters.FilterSet):
    user = django_filters.CharFilter(field_name='owner', lookup_expr='exact')
    has_balance = django_filters.BooleanFilter(method='filter_has_balance')

    class Meta:
        model = Wallet
        fields = ('user', 'has_balance')

    @staticmethod
    def filter_has_balance(queryset, name, value):
        if value:
            return queryset.filter(balance__gt=0)
        return queryset
