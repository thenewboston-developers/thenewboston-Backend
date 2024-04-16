from rest_framework.routers import SimpleRouter

from thenewboston.users.views.user import UserViewSet

router = SimpleRouter(trailing_slash=False)
router.register('users', UserViewSet)

urlpatterns = router.urls
