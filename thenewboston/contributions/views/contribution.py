from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from ..models import Contribution
from ..serializers.contribution import ContributionSerializer


class ContributionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Contribution.objects.all()
    serializer_class = ContributionSerializer
