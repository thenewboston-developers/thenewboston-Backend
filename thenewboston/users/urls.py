from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views.stats import StatsAPIView
from .views.user import UserViewSet
from .views.user_search import user_search

router = SimpleRouter(trailing_slash=False)
router.register('users', UserViewSet)

urlpatterns = [
    # Keep users/search before router.urls to prevent it from being matched as users/<pk>
    path('users/search', user_search, name='user-search'),
    path('', include(router.urls)),
    path('user/<int:user_id>/stats', StatsAPIView.as_view(), name='user-stats'),
]
