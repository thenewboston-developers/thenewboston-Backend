from rest_framework.routers import SimpleRouter

from .views.conversation import ConversationViewSet

router = SimpleRouter(trailing_slash=False)
router.register('conversations', ConversationViewSet)

urlpatterns = router.urls
