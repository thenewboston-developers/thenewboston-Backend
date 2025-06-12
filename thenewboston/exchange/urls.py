from django.urls import path
from rest_framework.routers import SimpleRouter

from .views.asset_pair import AssetPairViewSet
from .views.chart_data import ChartDataView
from .views.exchange_order import ExchangeOrderViewSet
from .views.trade import TradeViewSet

router = SimpleRouter(trailing_slash=False)
router.register('asset-pairs', AssetPairViewSet)
router.register('exchange-orders', ExchangeOrderViewSet)
router.register('trades', TradeViewSet)

urlpatterns = [
    path('chart-data', ChartDataView.as_view(), name='chart-data'),
] + router.urls
