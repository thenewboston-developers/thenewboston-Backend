from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectFollowerOrReadOnly

from ..models import Follower
from ..serializers.follower import FollowerCreateSerializer, FollowerReadSerializer


class FollowerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectFollowerOrReadOnly]
    queryset = Follower.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        follower = serializer.save()
        read_serializer = FollowerReadSerializer(follower, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action == 'create':
            return FollowerCreateSerializer

        return FollowerReadSerializer
