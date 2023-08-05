from rest_framework.routers import SimpleRouter

from .views.comment import CommentViewSet
from .views.post import PostViewSet

router = SimpleRouter(trailing_slash=False)
router.register('comments', CommentViewSet)
router.register('posts', PostViewSet)

urlpatterns = router.urls
