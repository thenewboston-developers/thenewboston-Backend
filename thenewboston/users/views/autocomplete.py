from rest_framework import viewsets

from ..models import User
from ..serializers.user import UserReadSerializer


class AutocompleteAPIView(viewsets.ModelViewSet):
    queryset = User.objects.all()

    queryset = User.objects.all()
    serializer_class = UserReadSerializer

    def get_queryset(self):
        username = self.request.query_params.get('username', None)
        if username is not None:
            return User.objects.filter(username=username)
        return User.objects.all()
