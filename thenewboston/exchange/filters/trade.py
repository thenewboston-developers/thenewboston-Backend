import django_filters

from ..models import Trade


class TradeFilter(django_filters.FilterSet):
    # TODO(dmu) MEDIUM: `buy_order__primary_currency` and `buy_order__secondary_currency`
    #                   are kept for backward compatibility. Consider removal
    buy_order__primary_currency = django_filters.NumberFilter(field_name='buy_order__asset_pair__primary_currency')
    buy_order__secondary_currency = django_filters.NumberFilter(field_name='buy_order__asset_pair__secondary_currency')

    # TODO(dmu) MEDIUM: Consider removal migration of `buy_order__asset_pair__primary_currency` and
    #                   `buy_order__asset_pair__secondary_currency` to `buy_order__asset_pair`.
    #                   Otherwise consider introduction of https://pypi.org/project/djangorestframework-filters/
    buy_order__asset_pair__primary_currency = django_filters.NumberFilter(
        field_name='buy_order__asset_pair__primary_currency'
    )
    buy_order__asset_pair__secondary_currency = django_filters.NumberFilter(
        field_name='buy_order__asset_pair__secondary_currency'
    )

    buy_order__asset_pair = django_filters.NumberFilter(field_name='buy_order__asset_pair')

    class Meta:
        model = Trade
        fields = {
            # TODO(dmu) LOW: Are these definitions excessive?
            'buy_order': ['exact'],
            'sell_order': ['exact'],
            'buy_order__asset_pair__primary_currency': ['exact'],
            'buy_order__asset_pair__secondary_currency': ['exact'],
            'buy_order__asset_pair': ['exact'],
        }
