from rest_framework.routers import SimpleRouter

from .views.currency import CurrencyViewSet
from .views.mint import MintViewSet

router = SimpleRouter(trailing_slash=False)
router.register('currencies', CurrencyViewSet)
router.register('mints', MintViewSet)

urlpatterns = router.urls
