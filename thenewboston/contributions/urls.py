from rest_framework.routers import SimpleRouter

from .views.contribution import ContributionViewSet, TopContributorsViewSet

router = SimpleRouter(trailing_slash=False)
router.register('contributions', ContributionViewSet)
router.register('top_contributors', TopContributorsViewSet)

urlpatterns = router.urls
