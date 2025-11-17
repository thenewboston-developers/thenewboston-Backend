from rest_framework.routers import SimpleRouter

from .views import BonsaiViewSet

router = SimpleRouter(trailing_slash=False)
router.register('bonsais', BonsaiViewSet)

urlpatterns = router.urls
