from django.utils import timezone
from rest_framework import serializers

from thenewboston.general.guest_games import GUEST_PLAYER, guest_session, owns_guest_match
from thenewboston.general.serializers import BaseModelSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..enums import MatchStatus
from ..models import ConnectFiveMatch, ConnectFiveMatchPlayer
from ..services.clocks import active_side


class ConnectFiveMatchPlayerSerializer(BaseModelSerializer):
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        return (
            GUEST_PLAYER
            if obj.is_guest
            else (UserReadSerializer(obj.user, context=self.context).data if obj.user else None)
        )

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
    player_a = serializers.SerializerMethodField()
    guest_mode = serializers.SerializerMethodField()
    your_side = serializers.SerializerMethodField()
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
            'guest_mode',
            'guest_session_id',
            'your_side',
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
        return active_side(obj)

    def get_guest_mode(self, obj):
        return bool(obj.guest_session_id)

    def get_player_a(self, obj):
        return GUEST_PLAYER if obj.guest_session_id else UserReadSerializer(obj.player_a, context=self.context).data

    def get_your_side(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        if obj.guest_session_id:
            return 'a' if owns_guest_match(obj, guest_session(request)) else None
        if request.user.is_authenticated:
            if obj.player_a_id == request.user.id:
                return 'a'
            if obj.player_b_id == request.user.id:
                return 'b'
        return None

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
