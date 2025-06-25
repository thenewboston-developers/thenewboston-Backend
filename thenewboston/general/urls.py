from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views.frontend_deployment import FrontendDeploymentViewSet

router = DefaultRouter()
router.register(r'deployments', FrontendDeploymentViewSet, basename='deployment')

urlpatterns = [
    path('', include(router.urls)),
]
