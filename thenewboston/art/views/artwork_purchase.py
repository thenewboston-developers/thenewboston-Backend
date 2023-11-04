from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import ArtworkTransfer
from ..serializers.artwork_purchase import ArtworkPurchaseSerializer
from ..serializers.artwork_transfer import ArtworkTransferReadSerializer


class ArtworkPurchaseViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    queryset = ArtworkTransfer.objects.all()

    @staticmethod
    def create(request):
        serializer = ArtworkPurchaseSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        artwork_transfer = serializer.save()
        read_serializer = ArtworkTransferReadSerializer(artwork_transfer, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)
