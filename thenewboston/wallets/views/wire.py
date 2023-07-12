from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from ..models import Wire
from ..serializers.wire import WireSerializer


class WireViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Wire.objects.none()
    serializer_class = WireSerializer

    def get_queryset(self):
        return Wire.objects.filter(owner=self.request.user)
