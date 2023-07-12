from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from ..models import AssetPair
from ..serializers.asset_pair import AssetPairSerializer


class AssetPairViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = AssetPair.objects.all()
    serializer_class = AssetPairSerializer
