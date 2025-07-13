from django.urls import path
from rest_framework.routers import SimpleRouter

from .views.currency import CurrencyViewSet
from .views.currency_balance import CurrencyBalanceListView
from .views.mint import MintViewSet
from .views.mint_chart_data import MintChartDataView
from .views.total_amount_minted import TotalAmountMintedView
from .views.whitepaper import WhitepaperViewSet

router = SimpleRouter(trailing_slash=False)
router.register('currencies', CurrencyViewSet)
router.register('mints', MintViewSet)
router.register('whitepapers', WhitepaperViewSet, basename='whitepaper')

urlpatterns = router.urls + [
    path('currency-balances', CurrencyBalanceListView.as_view(), name='currency-balances'),
    path('mint-chart-data', MintChartDataView.as_view(), name='mint-chart-data'),
    path('total-amount-minted', TotalAmountMintedView.as_view(), name='total-amount-minted'),
]
