from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from ..filters.asset_pair import AssetPairFilter
from ..models import AssetPair
from ..serializers.asset_pair import AssetPairSerializer


class AssetPairViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = AssetPairFilter
    permission_classes = [IsAuthenticated]
    queryset = AssetPair.objects.all()
    serializer_class = AssetPairSerializer
