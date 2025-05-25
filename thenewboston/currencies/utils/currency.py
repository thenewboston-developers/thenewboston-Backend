from django.conf import settings

from thenewboston.currencies.models import Currency


def get_default_currency():
    return Currency.objects.get(ticker=settings.DEFAULT_CURRENCY_TICKER)
