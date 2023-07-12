from rest_framework.routers import SimpleRouter

from .views.wallet import WalletViewSet
from .views.wire import WireViewSet

router = SimpleRouter(trailing_slash=False)
router.register('wallets', WalletViewSet)
router.register('wires', WireViewSet)

urlpatterns = router.urls
