from rest_framework.routers import SimpleRouter

from .views.wallet import WalletViewSet

router = SimpleRouter(trailing_slash=False)
router.register('wallets', WalletViewSet)

urlpatterns = router.urls
