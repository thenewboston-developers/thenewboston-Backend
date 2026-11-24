from django.utils import timezone
from rest_framework import serializers

from thenewboston.general.serializers import BaseModelSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..enums import MatchStatus
from ..models import ConnectFiveMatch, ConnectFiveMatchPlayer


class ConnectFiveMatchPlayerSerializer(BaseModelSerializer):
    user = UserReadSerializer(read_only=True)
    remaining_spend = serializers.SerializerMethodField()

    class Meta:
        model = ConnectFiveMatchPlayer
        fields = (
            'inventory_bomb',
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
    active_side = serializers.SerializerMethodField()
    computer_name = serializers.SerializerMethodField()
    rematch_of = serializers.PrimaryKeyRelatedField(source='computer_rematch_of', read_only=True)
    server_time = serializers.SerializerMethodField()
    winner_side = serializers.SerializerMethodField()
    player_a = UserReadSerializer(read_only=True)
    player_b = UserReadSerializer(read_only=True)
    players = ConnectFiveMatchPlayerSerializer(many=True, read_only=True)

    class Meta:
        model = ConnectFiveMatch
        fields = (
            'active_player',
            'active_side',
            'computer_name',
            'computer_reward',
            'difficulty',
            'mode',
            'rematch_of',
            'server_time',
            'version',
            'winner_side',
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

    @staticmethod
    def get_active_side(obj):
        if obj.status != MatchStatus.ACTIVE:
            return None
        return 'a' if obj.active_player_id == obj.player_a_id else 'b'

    @staticmethod
    def get_computer_name(obj):
        return 'Computer' if obj.mode == 'computer' else None

    @staticmethod
    def get_server_time(obj):
        return timezone.now()

    @staticmethod
    def get_winner_side(obj):
        if obj.mode == 'computer':
            return obj.winner_side
        if obj.winner_id is None:
            return None
        return 'a' if obj.winner_id == obj.player_a_id else 'b'
