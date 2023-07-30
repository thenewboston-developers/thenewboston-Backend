from rest_framework import permissions, viewsets
from rest_framework.response import Response

from ..models import InvitationLimit
from ..serializers.invitation_limit import InvitationLimitSerializer


class InvitationLimitViewSet(viewsets.GenericViewSet, viewsets.mixins.RetrieveModelMixin):
    permission_classes = [permissions.IsAuthenticated]
    queryset = InvitationLimit.objects.none()
    serializer_class = InvitationLimitSerializer

    def retrieve(self, request, *args, **kwargs):
        queryset = InvitationLimit.objects.filter(owner=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
