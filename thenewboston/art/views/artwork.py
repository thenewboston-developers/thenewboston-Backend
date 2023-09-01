from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Artwork
from ..serializers.artwork import ArtworkReadSerializer, ArtworkWriteSerializer


class ArtworkViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Artwork.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        artwork = serializer.save()
        read_serializer = ArtworkReadSerializer(artwork, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return ArtworkWriteSerializer

        return ArtworkReadSerializer
