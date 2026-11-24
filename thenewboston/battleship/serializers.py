from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from thenewboston.general.guest_games import GUEST_PLAYER, guest_session

from .models import BattleshipMatch
from .rules import BOARD_SIZE, SHIP_LENGTHS, opponent, sunk_ships
from .services import player_side


class MatchCreateSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=['computer', 'human'])
    opponent_id = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True), required=False, source='opponent'
    )
    difficulty = serializers.ChoiceField(choices=['easy', 'normal', 'hard'], default='normal')
    stake_amount = serializers.IntegerField(min_value=0, max_value=1000000000, default=0)
    time_limit_seconds = serializers.ChoiceField(choices=[300, 600, 900, 1800], default=900)

    def validate(self, attrs):
        if not self.context['request'].user.is_authenticated and attrs['mode'] != 'computer':
            raise serializers.ValidationError('Sign in to challenge another player.')
        if attrs['mode'] == 'human':
            if not attrs.get('opponent'):
                raise serializers.ValidationError({'opponent_id': 'Choose an opponent.'})
            if attrs['opponent'] == self.context['request'].user:
                raise serializers.ValidationError({'opponent_id': 'You cannot challenge yourself.'})
        elif attrs['stake_amount'] or attrs.get('opponent'):
            raise serializers.ValidationError('Computer practice is free and cannot have a human opponent.')
        return attrs


class MatchActionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class ShipSerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=list(SHIP_LENGTHS))
    row = serializers.IntegerField(min_value=0, max_value=BOARD_SIZE - 1)
    column = serializers.IntegerField(min_value=0, max_value=BOARD_SIZE - 1)
    orientation = serializers.ChoiceField(choices=['horizontal', 'vertical'])


class MatchPlaceSerializer(MatchActionSerializer):
    ships = ShipSerializer(many=True, min_length=5, max_length=5)


class MatchFireSerializer(MatchActionSerializer):
    row = serializers.IntegerField(min_value=0, max_value=BOARD_SIZE - 1)
    column = serializers.IntegerField(min_value=0, max_value=BOARD_SIZE - 1)


class MatchReadSerializer(serializers.ModelSerializer):
    guest_mode = serializers.SerializerMethodField()
    board = serializers.SerializerMethodField()
    computer_name = serializers.SerializerMethodField()
    guest = serializers.SerializerMethodField()
    guest_ready = serializers.SerializerMethodField()
    host = serializers.SerializerMethodField()
    host_ready = serializers.SerializerMethodField()
    server_time = serializers.SerializerMethodField()
    your_side = serializers.SerializerMethodField()

    class Meta:
        model = BattleshipMatch
        fields = [
            'id',
            'mode',
            'guest_mode',
            'guest_session_id',
            'difficulty',
            'computer_reward',
            'host',
            'guest',
            'computer_name',
            'your_side',
            'status',
            'phase',
            'stake_amount',
            'prize_pool_total',
            'version',
            'time_limit_seconds',
            'clock_host_ms',
            'clock_guest_ms',
            'active_side',
            'turn_started_at',
            'placement_deadline',
            'expires_at',
            'server_time',
            'created_date',
            'finished_at',
            'winner',
            'result_reason',
            'rematch_of',
            'board',
            'host_ready',
            'guest_ready',
            'last_shot',
        ]

    def get_guest_mode(self, obj):
        return bool(obj.guest_session_id)

    def _user(self, user):
        if user is None:
            return None
        avatar = user.avatar.url if user.avatar else None
        if avatar and (request := self.context.get('request')):
            avatar = request.build_absolute_uri(avatar)
        return {'id': user.id, 'username': user.username, 'avatar': avatar}

    def get_board(self, obj):
        side = self.get_your_side(obj)
        if side is None:
            return {'ships': [], 'shots': [], 'incoming_shots': [], 'opponent_sunk_ships': []}
        shots = getattr(obj, f'shots_{side}')
        other_side = opponent(side)
        return {
            'ships': getattr(obj, f'fleet_{side}'),
            'shots': shots,
            'incoming_shots': getattr(obj, f'shots_{other_side}'),
            'opponent_sunk_ships': sunk_ships(getattr(obj, f'fleet_{other_side}'), shots),
        }

    def get_computer_name(self, obj):
        return 'Computer' if obj.mode == 'computer' else None

    def get_guest(self, obj):
        return self._user(obj.guest)

    def get_guest_ready(self, obj):
        return bool(obj.fleet_guest)

    def get_host(self, obj):
        return GUEST_PLAYER if obj.guest_session_id else self._user(obj.host)

    def get_host_ready(self, obj):
        return bool(obj.fleet_host)

    def get_server_time(self, obj):
        return timezone.now()

    def get_your_side(self, obj):
        request = self.context.get('request')
        return player_side(obj, request.user.id, guest_session(request)) if request else None
