from rest_framework.routers import SimpleRouter

from .views.currency import CurrencyViewSet

router = SimpleRouter(trailing_slash=False)
router.register('currencies', CurrencyViewSet)

urlpatterns = router.urls
