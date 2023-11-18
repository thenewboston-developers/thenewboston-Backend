from rest_framework.routers import SimpleRouter

from .views.comment import CommentViewSet
from .views.follower import FollowerViewSet
from .views.post import PostViewSet

router = SimpleRouter(trailing_slash=False)
router.register('comments', CommentViewSet)
router.register('followers', FollowerViewSet)
router.register('posts', PostViewSet)

urlpatterns = router.urls
