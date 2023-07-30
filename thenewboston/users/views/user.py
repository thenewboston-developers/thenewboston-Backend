from rest_framework import status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.authentication import get_user_auth_data
from thenewboston.general.permissions import IsSelfOrReadOnly

from ..models import User
from ..serializers.user import UserReadSerializer, UserUpdateSerializer, UserWriteSerializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()

    def get_parsers(self):
        if self.request.method == 'POST':
            self.parser_classes = [JSONParser]
        elif self.request.method in ['PATCH', 'PUT']:
            self.parser_classes = [MultiPartParser, FormParser]

        return [parser() for parser in self.parser_classes]

    def get_permissions(self):
        if self.request.method == 'POST':
            self.permission_classes = [AllowAny]
        elif self.request.method in ['PATCH', 'PUT']:
            self.permission_classes = [IsAuthenticated, IsSelfOrReadOnly]

        return [permission() for permission in self.permission_classes]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserWriteSerializer
        elif self.request.method in ['PATCH', 'PUT']:
            return UserUpdateSerializer

        return UserReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(get_user_auth_data(user), status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        read_serializer = UserReadSerializer(instance, context={'request': request})

        return Response(read_serializer.data)
