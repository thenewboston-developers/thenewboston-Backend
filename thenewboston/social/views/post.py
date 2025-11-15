from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..filters.post import PostFilter
from ..models import Post
from ..serializers.post import PostReadSerializer, PostWriteSerializer
from ..utils.mentions import notify_mentioned_users_in_post


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

        mentioned_user_ids = getattr(post, '_new_mention_ids', None)
        if mentioned_user_ids:
            transaction.on_commit(
                lambda post=post, mentioned_user_ids=mentioned_user_ids: notify_mentioned_users_in_post(
                    post=post, mentioned_user_ids=mentioned_user_ids, request=request
                )
            )

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return PostWriteSerializer

        return PostReadSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ['retrieve', 'list']:
            queryset = queryset.prefetch_related(
                'comments__mentioned_users',
                'comments__owner',
                'comments__price_currency',
                'likes',
                'mentioned_users',
                'owner',
                'price_currency',
                'recipient',
            )

        return queryset

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated], url_path='tip-amounts')
    def tip_amounts(self, request, pk=None):
        post = self.get_object()
        serializer = PostReadSerializer(post, context={'request': request})
        tip_amounts = serializer.get_tip_amounts(post)

        return Response({'tip_amounts': tip_amounts})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        post = serializer.save()

        new_mention_ids = getattr(post, '_new_mention_ids', None)
        if new_mention_ids:
            transaction.on_commit(
                lambda post=post, mentioned_user_ids=new_mention_ids: notify_mentioned_users_in_post(
                    post=post, mentioned_user_ids=mentioned_user_ids, request=request
                )
            )

        read_serializer = PostReadSerializer(post, context={'request': request})

        return Response(read_serializer.data)
