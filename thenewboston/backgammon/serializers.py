from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from .models import BackgammonMatch
from .rules import legal_turns


class MatchCreateSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=['computer', 'human'])
    opponent_id = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True), required=False, source='opponent'
    )
    difficulty = serializers.ChoiceField(choices=['easy', 'normal', 'hard'], default='normal')
    stake_amount = serializers.IntegerField(min_value=0, max_value=1000000000, default=0)
    target_score = serializers.ChoiceField(choices=[1, 3, 5], default=3)
    time_limit_seconds = serializers.ChoiceField(choices=[300, 600, 900, 1800], default=900)

    def validate(self, attrs):
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


class MatchMoveSerializer(MatchActionSerializer):
    moves = serializers.ListField(child=serializers.DictField(), max_length=4)


class DoubleResponseSerializer(MatchActionSerializer):
    accept = serializers.BooleanField()


class MatchReadSerializer(serializers.ModelSerializer):
    black = serializers.SerializerMethodField()
    can_double = serializers.SerializerMethodField()
    clock_side = serializers.SerializerMethodField()
    computer_name = serializers.SerializerMethodField()
    last_game_result = serializers.SerializerMethodField()
    last_turn = serializers.SerializerMethodField()
    legal_turns = serializers.SerializerMethodField()
    scores = serializers.SerializerMethodField()
    server_time = serializers.SerializerMethodField()
    white = serializers.SerializerMethodField()

    class Meta:
        model = BackgammonMatch
        fields = [
            'id',
            'mode',
            'difficulty',
            'computer_reward',
            'white',
            'black',
            'computer_name',
            'status',
            'phase',
            'stake_amount',
            'prize_pool_total',
            'target_score',
            'scores',
            'game_number',
            'board',
            'active_side',
            'dice',
            'cube_value',
            'cube_owner',
            'double_offered_by',
            'is_crawford',
            'crawford_used',
            'version',
            'time_limit_seconds',
            'clock_white_ms',
            'clock_black_ms',
            'clock_side',
            'turn_started_at',
            'server_time',
            'expires_at',
            'winner',
            'game_winner',
            'result_points',
            'result_reason',
            'last_game_result',
            'last_turn',
            'legal_turns',
            'can_double',
            'created_date',
            'finished_at',
            'next_game_at',
            'rematch_of',
        ]

    def get_fields(self):
        fields = super().get_fields()
        if not self.context.get('detail'):
            # Lobby lists do not need presentation events or a query per match.
            fields.pop('last_turn')
        return fields

    def _user(self, user):
        if user is None:
            return None
        avatar = None
        if user.avatar:
            avatar = user.avatar.url
            if request := self.context.get('request'):
                avatar = request.build_absolute_uri(avatar)
        return {'id': user.id, 'username': user.username, 'avatar': avatar}

    def _side(self, obj):
        from .services import player_side

        request = self.context.get('request')
        return player_side(obj, request.user.id) if request and request.user.is_authenticated else None

    def get_black(self, obj):
        return self._user(obj.black)

    def get_can_double(self, obj):
        from .services import can_double

        return self._side(obj) == obj.active_side and can_double(obj)

    def get_clock_side(self, obj):
        from .services import clock_side

        return clock_side(obj)

    def get_computer_name(self, obj):
        return 'Computer' if obj.mode == 'computer' else None

    def get_last_game_result(self, obj):
        if not obj.game_winner:
            return None
        return {'winner': obj.game_winner, 'points': obj.result_points, 'reason': obj.result_reason}

    def get_last_turn(self, obj):
        # CPU roll + move commit together and clear the live dice. The event
        # retains the actual dice and checker moves for clients between polls.
        # A game-start boundary prevents replaying a previous game's last turn.
        # Cap the query at the serialized snapshot, which may already be stale.
        event = (
            obj.events.filter(
                event_type__in=['move', 'created', 'accepted', 'next_game'],
                version__lte=obj.version,
            )
            .order_by('-version')
            .values('event_type', 'version', 'payload')
            .first()
        )
        if not event or event['event_type'] != 'move':
            return None
        payload = event['payload']
        return {
            'version': event['version'],
            'side': payload['side'],
            'dice': payload['dice'],
            'moves': payload['moves'],
        }

    def get_legal_turns(self, obj):
        if self.context.get('detail') and obj.phase == 'moving' and self._side(obj) == obj.active_side:
            return legal_turns(obj.board, obj.active_side, obj.dice)
        return []

    def get_scores(self, obj):
        return {'white': obj.score_white, 'black': obj.score_black}

    def get_server_time(self, obj):
        return timezone.now()

    def get_white(self, obj):
        return self._user(obj.white)
