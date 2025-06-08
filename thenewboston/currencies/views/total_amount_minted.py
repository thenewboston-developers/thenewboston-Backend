from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from ..filters.total_amount_minted import TotalAmountMintedFilter
from ..models import Currency
from ..serializers.total_amount_minted import TotalAmountMintedSerializer


class TotalAmountMintedViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    filterset_class = TotalAmountMintedFilter
    permission_classes = [IsAuthenticated]
    queryset = Currency.objects.all()
    serializer_class = TotalAmountMintedSerializer
