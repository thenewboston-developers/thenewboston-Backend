from django.urls import path
from rest_framework.routers import SimpleRouter

from .guest_games import GuestGameSessionView
from .views.frontend_deployment import FrontendDeploymentViewSet

router = SimpleRouter(trailing_slash=False)
router.register('frontend-deployments', FrontendDeploymentViewSet)

urlpatterns = [path('guest-games/session', GuestGameSessionView.as_view()), *router.urls]
