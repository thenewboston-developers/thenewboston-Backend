from rest_framework.routers import SimpleRouter

from .views.asset_pair import AssetPairViewSet
from .views.exchange_order import ExchangeOrderViewSet
from .views.trade import TradeViewSet

router = SimpleRouter(trailing_slash=False)
router.register('asset-pairs', AssetPairViewSet)
router.register('exchange-orders', ExchangeOrderViewSet)
router.register('trades', TradeViewSet)

urlpatterns = router.urls
