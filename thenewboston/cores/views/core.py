from rest_framework import status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Core
from ..serializers.core import CoreReadSerializer, CoreWriteSerializer


class CoreViewSet(viewsets.ModelViewSet):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Core.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        core = serializer.save()
        read_serializer = CoreReadSerializer(core, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return CoreWriteSerializer

        return CoreReadSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        core = serializer.save()
        read_serializer = CoreReadSerializer(core, context={'request': request})

        return Response(read_serializer.data)
