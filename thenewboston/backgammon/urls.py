from rest_framework.routers import SimpleRouter

from .views import BackgammonMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('backgammon/matches', BackgammonMatchViewSet, basename='backgammon-match')
urlpatterns = router.urls
