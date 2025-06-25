from rest_framework.routers import SimpleRouter

from .views.frontend_deployment import FrontendDeploymentViewSet

router = SimpleRouter(trailing_slash=False)
router.register('frontend-deployments', FrontendDeploymentViewSet)

urlpatterns = router.urls
