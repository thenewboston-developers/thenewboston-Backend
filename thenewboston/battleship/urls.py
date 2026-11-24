from rest_framework.routers import SimpleRouter

from .views import BattleshipMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('battleship/matches', BattleshipMatchViewSet, basename='battleship-match')
urlpatterns = router.urls
