from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import IsAuthenticated

from thenewboston.general.views.base import CustomGenericViewSet

from ..models import ConnectFiveEloSnapshot
from ..serializers import ConnectFiveEloSnapshotSerializer


class ConnectFiveEloSnapshotViewSet(ListModelMixin, CustomGenericViewSet):
    limit_to_user_id_field = 'user_id'
    permission_classes = [IsAuthenticated]
    queryset = ConnectFiveEloSnapshot.objects.order_by('snapshot_date')
    serializer_class = ConnectFiveEloSnapshotSerializer
