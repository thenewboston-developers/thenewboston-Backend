import django_filters

from thenewboston.currencies.models import Currency, Mint


class MintChartDataFilter(django_filters.FilterSet):
    currency = django_filters.NumberFilter(method='filter_currency', required=True)

    class Meta:
        model = Mint
        fields = ('currency',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currency_obj = None

    def filter_currency(self, queryset, name, value):
        try:
            currency = Currency.objects.get(pk=value)
            self.currency_obj = currency
            return queryset.filter(currency=currency)
        except Currency.DoesNotExist:
            self.currency_obj = None
            return queryset.none()
