from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views.comment import CommentViewSet
from .views.follower import FollowerViewSet
from .views.post import PostViewSet
from .views.post_reaction import PostReactionCreateUpdateView

router = SimpleRouter(trailing_slash=False)
router.register('comments', CommentViewSet)
router.register('followers', FollowerViewSet)
router.register('posts', PostViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('post-reaction/', PostReactionCreateUpdateView.as_view(), name='post-reaction-create-update'),
]
