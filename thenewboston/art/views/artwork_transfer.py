from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import ArtworkTransfer
from ..serializers.artwork_transfer import ArtworkTransferReadSerializer, ArtworkTransferWriteSerializer


class ArtworkTransferViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = ArtworkTransfer.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        transfer = serializer.save()
        read_serializer = ArtworkTransferReadSerializer(transfer, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Deletion of ArtworkTransfers is not allowed.'}, status=status.HTTP_403_FORBIDDEN)

    def get_serializer_class(self):
        if self.action in ['create']:
            return ArtworkTransferWriteSerializer

        return ArtworkTransferReadSerializer

    def partial_update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Updating of ArtworkTransfers is not allowed.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    def update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Updating of ArtworkTransfers is not allowed.'},
            status=status.HTTP_403_FORBIDDEN,
        )
