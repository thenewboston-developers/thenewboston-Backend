from rest_framework.routers import SimpleRouter

from .views.notification import NotificationViewSet

router = SimpleRouter(trailing_slash=False)
router.register('notifications', NotificationViewSet)

urlpatterns = router.urls
