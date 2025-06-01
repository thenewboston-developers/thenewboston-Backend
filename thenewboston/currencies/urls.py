from django.urls import path
from rest_framework.routers import SimpleRouter

from .views.currency import CurrencyViewSet
from .views.currency_balance import CurrencyBalanceListView
from .views.mint import MintViewSet

router = SimpleRouter(trailing_slash=False)
router.register('currencies', CurrencyViewSet)
router.register('mints', MintViewSet)

urlpatterns = [
    path('currency-balances', CurrencyBalanceListView.as_view(), name='currency-balances'),
] + router.urls
