from rest_framework.routers import SimpleRouter

from .views.asset_pair import AssetPairViewSet
from .views.order import OrderViewSet

router = SimpleRouter(trailing_slash=False)
router.register('asset_pairs', AssetPairViewSet)
router.register('orders', OrderViewSet)

urlpatterns = router.urls
