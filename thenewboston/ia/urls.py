from rest_framework.routers import SimpleRouter

from .views.conversation import ConversationViewSet
from .views.message import MessageViewSet

router = SimpleRouter(trailing_slash=False)
router.register('conversations', ConversationViewSet)
router.register('messages', MessageViewSet)

urlpatterns = router.urls
