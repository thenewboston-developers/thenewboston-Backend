from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from ..models import InvitationLimit
from ..serializers.invitation_limit import InvitationLimitSerializer


class InvitationLimitViewSet(viewsets.GenericViewSet, viewsets.mixins.RetrieveModelMixin):
    permission_classes = [permissions.IsAuthenticated]
    queryset = InvitationLimit.objects.none()
    serializer_class = InvitationLimitSerializer

    def retrieve(self, request, *args, **kwargs):
        try:
            owner_id = int(kwargs['pk'])
        except ValueError:
            return Response({'error': 'Invalid ID provided.'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = InvitationLimit.objects.filter(owner=owner_id).first()

        if queryset is None:
            return Response({'error': 'No InvitationLimit found with this ID.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(queryset)
        return Response(serializer.data)
