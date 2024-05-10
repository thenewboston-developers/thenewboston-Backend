from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views.conversation import ConversationViewSet
from .views.ia import IaAPIView
from .views.message import MessageViewSet

router = SimpleRouter(trailing_slash=False)
router.register('conversations', ConversationViewSet)
router.register('messages', MessageViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('ia', IaAPIView.as_view(), name='ia'),
]
