from rest_framework.routers import SimpleRouter

from .views.contribution import ContributionViewSet

router = SimpleRouter(trailing_slash=False)
router.register('contributions', ContributionViewSet)

urlpatterns = router.urls
