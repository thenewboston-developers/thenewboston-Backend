from rest_framework.routers import SimpleRouter

from .views import CheckersMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('checkers/matches', CheckersMatchViewSet, basename='checkers-match')
urlpatterns = router.urls
