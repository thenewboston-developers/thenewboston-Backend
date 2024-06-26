from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..filters.artwork import ArtworkFilter
from ..models import Artwork
from ..serializers.artwork import ArtworkReadSerializer, ArtworkWriteSerializer


class ArtworkViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = ArtworkFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Artwork.objects.all().order_by('-created_date')

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

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        artwork = serializer.save()
        read_serializer = ArtworkReadSerializer(artwork, context={'request': request})

        return Response(read_serializer.data)
