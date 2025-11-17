from rest_framework import viewsets

from thenewboston.general.permissions import IsAdminOrReadOnly

from ..models import Bonsai
from ..serializers import BonsaiSerializer


class BonsaiViewSet(viewsets.ModelViewSet):
    lookup_field = 'slug'
    permission_classes = [IsAdminOrReadOnly]
    queryset = Bonsai.objects.all().select_related('price_currency').prefetch_related('highlights', 'images')
    serializer_class = BonsaiSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated or not user.is_staff:
            return queryset.filter(status=Bonsai.Status.PUBLISHED)

        status_param = self.request.query_params.get('status')
        if status_param in Bonsai.Status.values:
            return queryset.filter(status=status_param)

        return queryset
