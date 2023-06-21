from rest_framework.routers import SimpleRouter

from .views.asset_pair import AssetPairViewSet

router = SimpleRouter(trailing_slash=False)
router.register('asset_pairs', AssetPairViewSet)

urlpatterns = router.urls
