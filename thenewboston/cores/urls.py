from rest_framework.routers import SimpleRouter

from .views.core import CoreViewSet

router = SimpleRouter(trailing_slash=False)
router.register('cores', CoreViewSet)

urlpatterns = router.urls
