import django_filters

from thenewboston.wallets.models import Wallet

from ..models import Currency


class CurrencyFilter(django_filters.FilterSet):
    no_wallet = django_filters.BooleanFilter(method='filter_no_wallet')

    class Meta:
        model = Currency
        fields = ('no_wallet',)

    def filter_no_wallet(self, queryset, name, value):
        if value and self.request.user.is_authenticated:
            user_wallet_currencies = Wallet.objects.filter(owner=self.request.user).values_list(
                'currency_id', flat=True
            )
            return queryset.exclude(id__in=user_wallet_currencies)
        return queryset
