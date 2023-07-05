from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from ..models import Transfer
from ..serializers.transfer import TransferSerializer


class TransferViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Transfer.objects.none()
    serializer_class = TransferSerializer

    def get_queryset(self):
        return Transfer.objects.filter(owner=self.request.user)
