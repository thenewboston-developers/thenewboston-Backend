from rest_framework import status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from thenewboston.general.authentication import get_user_auth_data
from thenewboston.general.permissions import IsSelfOrReadOnly

from ..models import User
from ..serializers.user import UserReadSerializer, UserUpdateSerializer, UserWriteSerializer


class UserViewSet(viewsets.ModelViewSet):
    # Accounts cannot be deleted through the API, so DELETE is not an allowed method
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    permission_classes = [IsAuthenticatedOrReadOnly, IsSelfOrReadOnly]
    queryset = User.objects.select_related('connect_five_stats')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(get_user_auth_data(user, request), status=status.HTTP_201_CREATED)

    def get_parsers(self):
        if self.request.method == 'POST':
            self.parser_classes = [JSONParser]
        elif self.request.method in ['PATCH', 'PUT']:
            self.parser_classes = [MultiPartParser, FormParser]

        return [parser() for parser in self.parser_classes]

    def get_permissions(self):
        # Creating an account is the only write that does not require authentication
        if self.request.method == 'POST':
            return [AllowAny()]

        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserWriteSerializer
        elif self.request.method in ['PATCH', 'PUT']:
            return UserUpdateSerializer

        return UserReadSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        read_serializer = UserReadSerializer(instance, context={'request': request})

        return Response(read_serializer.data)
