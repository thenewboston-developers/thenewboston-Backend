from django.urls import path
from rest_framework.routers import SimpleRouter

from .views.asset_pair import AssetPairViewSet
from .views.exchange_order import ExchangeOrderViewSet
from .views.trade import TradeViewSet
from .views.trade_history_item import TradeHistoryItemViewSet
from .views.trade_price_chart_data import TradePriceChartDataView

router = SimpleRouter(trailing_slash=False)
router.register('asset-pairs', AssetPairViewSet)
router.register('exchange-orders', ExchangeOrderViewSet)
router.register('trades', TradeViewSet)
router.register('trade-history-items', TradeHistoryItemViewSet)

urlpatterns = router.urls + [
    path('trade-price-chart-data', TradePriceChartDataView.as_view(), name='trade-price-chart-data'),
]
