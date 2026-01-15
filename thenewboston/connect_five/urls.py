from rest_framework.routers import SimpleRouter

from .views import ConnectFiveChallengeViewSet, ConnectFiveLeaderboardViewSet, ConnectFiveMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('connect-five/challenges', ConnectFiveChallengeViewSet)
router.register('connect-five/leaderboard', ConnectFiveLeaderboardViewSet, basename='connect-five-leaderboard')
router.register('connect-five/matches', ConnectFiveMatchViewSet)

urlpatterns = router.urls
