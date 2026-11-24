from rest_framework.routers import SimpleRouter

from .views import MancalaMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('mancala/matches', MancalaMatchViewSet, basename='mancala-match')
urlpatterns = router.urls
