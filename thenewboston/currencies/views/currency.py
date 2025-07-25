from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectOwnerOrReadOnly

from ..models import Currency
from ..serializers.currency import CurrencyReadSerializer, CurrencyWriteSerializer


class CurrencyViewSet(viewsets.ModelViewSet):
    ordering = ['-created_date']
    ordering_fields = ['ticker', 'created_date', 'modified_date']
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    queryset = Currency.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        currency = serializer.save()
        read_serializer = CurrencyReadSerializer(currency, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return CurrencyWriteSerializer

        return CurrencyReadSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.ticker == settings.DEFAULT_CURRENCY_TICKER:
            raise ValidationError({'detail': 'The default currency cannot be deleted.'})
        return super().destroy(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        currency = serializer.save()
        read_serializer = CurrencyReadSerializer(currency, context={'request': request})

        return Response(read_serializer.data)
