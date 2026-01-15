from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import IsAuthenticated

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.views.base import CustomGenericViewSet

from ..models import ConnectFiveStats
from ..serializers import ConnectFiveLeaderboardEntrySerializer


class ConnectFiveLeaderboardPagination(CustomPageNumberPagination):
    page_size = 25


class ConnectFiveLeaderboardViewSet(ListModelMixin, CustomGenericViewSet):
    pagination_class = ConnectFiveLeaderboardPagination
    permission_classes = [IsAuthenticated]
    queryset = (
        ConnectFiveStats.objects.select_related('user').filter(matches_played__gt=0).order_by('-elo', 'user__username')
    )
    serializer_class = ConnectFiveLeaderboardEntrySerializer
