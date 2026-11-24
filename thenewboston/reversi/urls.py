from rest_framework.routers import SimpleRouter

from .views import ReversiMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('reversi/matches', ReversiMatchViewSet, basename='reversi-match')
urlpatterns = router.urls
