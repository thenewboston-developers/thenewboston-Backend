from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectFollowerOrReadOnly

from ..filters.follower import FollowerFilter
from ..models import Follower
from ..serializers.follower import FollowerCreateSerializer, FollowerReadSerializer


class FollowerViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = FollowerFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated, IsObjectFollowerOrReadOnly]
    queryset = Follower.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        follower = serializer.save()
        read_serializer = FollowerReadSerializer(follower, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        following_id = kwargs.get('pk')
        follower = request.user
        follower_relationship = Follower.objects.filter(follower=follower, following_id=following_id)
        follower_relationship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_class(self):
        if self.action == 'create':
            return FollowerCreateSerializer

        return FollowerReadSerializer
