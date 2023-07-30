from rest_framework.routers import SimpleRouter

from .views.invitation import InvitationViewSet
from .views.invitation_limit import InvitationLimitViewSet

router = SimpleRouter(trailing_slash=False)
router.register('invitations', InvitationViewSet)
router.register('invitation_limits', InvitationLimitViewSet)

urlpatterns = router.urls
