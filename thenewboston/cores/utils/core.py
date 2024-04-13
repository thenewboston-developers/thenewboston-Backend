from django.conf import settings

from thenewboston.cores.models import Core


def get_default_core():
    return Core.objects.get(ticker=settings.DEFAULT_CORE_TICKER)
