from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..filters.whitepaper import WhitepaperFilter
from ..models import Whitepaper
from ..serializers.whitepaper import WhitepaperReadSerializer, WhitepaperWriteSerializer


class WhitepaperViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = WhitepaperFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Whitepaper.objects.all().order_by('-created_date')

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return WhitepaperWriteSerializer
        return WhitepaperReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        whitepaper = serializer.save()
        read_serializer = WhitepaperReadSerializer(whitepaper, context={'request': request})
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        whitepaper = serializer.save()
        read_serializer = WhitepaperReadSerializer(whitepaper, context={'request': request})
        return Response(read_serializer.data)
