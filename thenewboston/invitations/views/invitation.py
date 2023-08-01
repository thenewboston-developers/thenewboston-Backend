from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Invitation
from ..serializers.invitation import InvitationSerializer


class InvitationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    serializer_class = InvitationSerializer
    queryset = Invitation.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.recipient is not None:
            return Response({'detail': 'Cannot delete an invitation that has a recipient.'},
                            status=status.HTTP_400_BAD_REQUEST)

        self.perform_destroy(instance)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_queryset(self):
        return Invitation.objects.filter(owner=self.request.user)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.note = request.data.get('note', instance.note)
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
