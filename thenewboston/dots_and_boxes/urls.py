from rest_framework.routers import SimpleRouter

from .views import DotsAndBoxesMatchViewSet

router = SimpleRouter(trailing_slash=False)
router.register('dots-and-boxes/matches', DotsAndBoxesMatchViewSet, basename='dots-and-boxes-match')
urlpatterns = router.urls
