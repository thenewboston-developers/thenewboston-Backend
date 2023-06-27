from rest_framework.routers import SimpleRouter

from .views.asset_pair import AssetPairViewSet
from .views.order import OrderViewSet
from .views.trade import TradeViewSet

router = SimpleRouter(trailing_slash=False)
router.register('asset_pairs', AssetPairViewSet)
router.register('orders', OrderViewSet)
router.register('trades', TradeViewSet)

urlpatterns = router.urls
