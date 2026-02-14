import django_filters
from django.db.models import Q

from ..models import Wallet


class WalletFilter(django_filters.FilterSet):
    currency = django_filters.NumberFilter(field_name='currency')
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Wallet
        fields = ('currency', 'search')

    @staticmethod
    def filter_search(queryset, name, value):
        if not value:
            return queryset

        search_term = value.strip()
        if not search_term:
            return queryset

        return queryset.filter(Q(currency__domain__icontains=search_term) | Q(currency__ticker__icontains=search_term))
