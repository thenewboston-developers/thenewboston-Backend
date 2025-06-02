from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..filters.post import PostFilter
from ..models import Post
from ..serializers.post import PostReadSerializer, PostWriteSerializer


class PostViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = PostFilter
    pagination_class = CustomPageNumberPagination
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Post.objects.all().order_by('-created_date')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        post = serializer.save()
        read_serializer = PostReadSerializer(post, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return PostWriteSerializer

        return PostReadSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ['retrieve', 'list']:
            queryset = queryset.prefetch_related('owner', 'likes')

        return queryset

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        post = serializer.save()
        read_serializer = PostReadSerializer(post, context={'request': request})

        return Response(read_serializer.data)
