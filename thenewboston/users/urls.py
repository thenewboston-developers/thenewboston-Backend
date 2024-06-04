from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views.stats import StatsAPIView
from .views.user import UserViewSet

router = SimpleRouter(trailing_slash=False)
router.register('users', UserViewSet)
urlpatterns = router.urls

urlpatterns = [
    path('', include(router.urls)),
    path('user/<int:user_id>/stats', StatsAPIView.as_view(), name='user-stats'),
]
