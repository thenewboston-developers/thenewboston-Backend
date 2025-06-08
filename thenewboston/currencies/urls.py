from django.urls import path
from rest_framework.routers import SimpleRouter

from .views.currency import CurrencyViewSet
from .views.currency_balance import CurrencyBalanceListView
from .views.mint import MintViewSet
from .views.total_amount_minted import TotalAmountMintedViewSet

router = SimpleRouter(trailing_slash=False)
router.register('currencies', CurrencyViewSet)
router.register('mints', MintViewSet)
router.register('total-amount-minted', TotalAmountMintedViewSet, basename='total-amount-minted')

urlpatterns = [
    path('currency-balances', CurrencyBalanceListView.as_view(), name='currency-balances'),
] + router.urls
