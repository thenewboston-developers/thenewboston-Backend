from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from .models import CheckersMatch
from .rules import legal_moves
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
        if attrs['mode'] == 'human':
            if not attrs.get('opponent'):
                raise serializers.ValidationError({'opponent_id': 'Choose an opponent.'})
            if attrs['opponent'] == self.context['request'].user:
                raise serializers.ValidationError({'opponent_id': 'You cannot challenge yourself.'})
        elif attrs['stake_amount'] or attrs.get('opponent'):
            raise serializers.ValidationError('Computer play is free and cannot have a human opponent.')
        return attrs


class MatchActionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class MatchMoveSerializer(MatchActionSerializer):
    path = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=63), min_length=2, max_length=13)


class MatchReadSerializer(serializers.ModelSerializer):
    black = serializers.SerializerMethodField()
    computer_name = serializers.SerializerMethodField()
    legal_moves = serializers.SerializerMethodField()
    server_time = serializers.SerializerMethodField()
    white = serializers.SerializerMethodField()
    your_side = serializers.SerializerMethodField()

    class Meta:
        model = CheckersMatch
        fields = [
            'id',
            'mode',
            'difficulty',
            'computer_reward',
            'white',
            'black',
            'computer_name',
            'your_side',
            'status',
            'stake_amount',
            'prize_pool_total',
            'version',
            'time_limit_seconds',
            'clock_white_ms',
            'clock_black_ms',
            'active_side',
            'turn_started_at',
            'expires_at',
            'server_time',
            'created_date',
            'finished_at',
            'winner',
            'result_reason',
            'rematch_of',
            'board',
            'last_move',
            'legal_moves',
            'reversible_plies',
        ]

    def _user(self, user):
        if user is None:
            return None
        avatar = user.avatar.url if user.avatar else None
        if avatar and (request := self.context.get('request')):
            avatar = request.build_absolute_uri(avatar)
        return {'id': user.id, 'username': user.username, 'avatar': avatar}

    def get_black(self, obj):
        return self._user(obj.black)

    def get_computer_name(self, obj):
        return 'Computer' if obj.mode == 'computer' else None

    def get_legal_moves(self, obj):
        if self.context.get('detail') and obj.status == 'active' and self.get_your_side(obj) == obj.active_side:
            return legal_moves(obj.board, obj.active_side)
        return []

    def get_server_time(self, obj):
        return timezone.now()

    def get_white(self, obj):
        return self._user(obj.white)

    def get_your_side(self, obj):
        request = self.context.get('request')
        return player_side(obj, request.user.id) if request and request.user.is_authenticated else None
