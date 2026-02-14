import django_filters
from django.db.models import Q

from thenewboston.wallets.models import Wallet

from ..models import Currency


class CurrencyFilter(django_filters.FilterSet):
    no_wallet = django_filters.BooleanFilter(method='filter_no_wallet')
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Currency
        fields = ('no_wallet', 'search')

    def filter_no_wallet(self, queryset, name, value):
        if value and self.request.user.is_authenticated:
            user_wallet_currencies = Wallet.objects.filter(owner=self.request.user).values_list(
                'currency_id', flat=True
            )
            return queryset.exclude(id__in=user_wallet_currencies)
        return queryset

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset

        search_term = value.strip()
        if not search_term:
            return queryset

        return queryset.filter(
            Q(description__icontains=search_term)
            | Q(domain__icontains=search_term)
            | Q(owner__username__icontains=search_term)
            | Q(ticker__icontains=search_term)
        )
