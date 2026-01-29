from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import ConnectFiveStats


class ConnectFiveLeaderboardEntrySerializer(serializers.ModelSerializer):
    user = UserReadSerializer(read_only=True)

    class Meta:
        model = ConnectFiveStats
        fields = ('elo', 'losses', 'matches_played', 'user', 'wins')
