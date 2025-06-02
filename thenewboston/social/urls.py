from rest_framework.routers import SimpleRouter

from .views.comment import CommentViewSet
from .views.follower import FollowerViewSet
from .views.post import PostViewSet
from .views.post_like import PostActionViewSet, PostLikeViewSet

router = SimpleRouter(trailing_slash=False)
router.register('comments', CommentViewSet)
router.register('followers', FollowerViewSet)
router.register('posts', PostViewSet)
router.register('posts', PostActionViewSet, basename='post-actions')
router.register('post-likes', PostLikeViewSet)

urlpatterns = router.urls
