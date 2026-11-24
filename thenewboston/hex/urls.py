from rest_framework.routers import SimpleRouter

from .views import HexMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('hex/matches', HexMatchViewSet, basename='hex-match')
urlpatterns = router.urls
