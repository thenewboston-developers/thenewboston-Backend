from rest_framework.routers import SimpleRouter

from .views.comment import CommentViewSet
from .views.follower import FollowerViewSet
from .views.post import PostViewSet
from .views.post_like import PostLikeViewSet

router = SimpleRouter(trailing_slash=False)
router.register('comments', CommentViewSet)
router.register('followers', FollowerViewSet)
router.register('posts', PostViewSet)
router.register('posts', PostLikeViewSet, basename='post-likes')

urlpatterns = router.urls
