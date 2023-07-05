from rest_framework.routers import SimpleRouter

from .views.transfer import TransferViewSet

router = SimpleRouter(trailing_slash=False)
router.register('transfers', TransferViewSet)

urlpatterns = router.urls
