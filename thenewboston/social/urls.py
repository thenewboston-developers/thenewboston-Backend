from rest_framework.routers import SimpleRouter

from .views.post import PostViewSet

router = SimpleRouter(trailing_slash=False)
router.register('posts', PostViewSet)

urlpatterns = router.urls
