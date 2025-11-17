from rest_framework import viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from thenewboston.general.permissions import IsAdminOrReadOnly

from ..models import Bonsai
from ..serializers import BonsaiSerializer


class BonsaiViewSet(viewsets.ModelViewSet):
    lookup_field = 'slug'
    permission_classes = [IsAdminOrReadOnly]
    queryset = Bonsai.objects.all().select_related('price_currency').prefetch_related('highlights', 'images')
    serializer_class = BonsaiSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_object(self):
        lookup_value = self.kwargs.get(self.lookup_field)
        if lookup_value and str(lookup_value).isdigit():
            queryset = self.filter_queryset(self.get_queryset())
            return queryset.get(pk=lookup_value)
        return super().get_object()

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated or not user.is_staff:
            return queryset.filter(status=Bonsai.Status.PUBLISHED)

        status_param = self.request.query_params.get('status')
        if status_param in Bonsai.Status.values:
            return queryset.filter(status=status_param)

        return queryset
