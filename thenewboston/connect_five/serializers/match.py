from rest_framework import serializers

from thenewboston.general.serializers import BaseModelSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import ConnectFiveMatch, ConnectFiveMatchPlayer


class ConnectFiveMatchPlayerSerializer(BaseModelSerializer):
    user = UserReadSerializer(read_only=True)
    remaining_spend = serializers.SerializerMethodField()

    class Meta:
        model = ConnectFiveMatchPlayer
        fields = (
            'inventory_bomb',
            'inventory_cross4',
            'inventory_h2',
            'inventory_v2',
            'remaining_spend',
            'spent_total',
            'user',
        )

    @staticmethod
    def get_remaining_spend(obj):
        return max(obj.match.max_spend_amount - obj.spent_total, 0)


class ConnectFiveMatchReadSerializer(BaseModelSerializer):
    active_player = UserReadSerializer(read_only=True)
    player_a = UserReadSerializer(read_only=True)
    player_b = UserReadSerializer(read_only=True)
    players = ConnectFiveMatchPlayerSerializer(many=True, read_only=True)

    class Meta:
        model = ConnectFiveMatch
        fields = (
            'active_player',
            'board_state',
            'challenge',
            'clock_a_remaining_ms',
            'clock_b_remaining_ms',
            'created_date',
            'finished_at',
            'id',
            'max_spend_amount',
            'modified_date',
            'player_a',
            'player_a_elo_after',
            'player_a_elo_before',
            'player_b',
            'player_b_elo_after',
            'player_b_elo_before',
            'players',
            'prize_pool_total',
            'status',
            'time_limit_seconds',
            'turn_number',
            'turn_started_at',
            'winner',
        )
