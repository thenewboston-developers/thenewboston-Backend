from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination

from ..filters.mint import MintFilter
from ..models import Mint
from ..serializers.mint import MintReadSerializer, MintWriteSerializer


class MintViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = MintFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated]
    queryset = Mint.objects.all().order_by('-created_date')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        mint = serializer.save()
        read_serializer = MintReadSerializer(mint, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action == 'create':
            return MintWriteSerializer

        return MintReadSerializer
