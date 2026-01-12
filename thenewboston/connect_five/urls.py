from rest_framework.routers import SimpleRouter

from .views import ConnectFiveChallengeViewSet, ConnectFiveMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('connect-five/challenges', ConnectFiveChallengeViewSet)
router.register('connect-five/matches', ConnectFiveMatchViewSet)

urlpatterns = router.urls
