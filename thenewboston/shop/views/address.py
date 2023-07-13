from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Address
from ..serializers.address import AddressSerializer


class AddressViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    serializer_class = AddressSerializer
    queryset = Address.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        return Address.objects.filter(owner=self.request.user)
