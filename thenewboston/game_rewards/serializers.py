from rest_framework import serializers

from thenewboston.users.models import User

from .models import GameRewardDecision


class GameEarningsQuerySerializer(serializers.Serializer):
    game = serializers.ChoiceField(choices=GameRewardDecision._meta.get_field('game').choices)


class GameEarnerUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'avatar')


class GameEarningsLeaderboardSerializer(serializers.Serializer):
    rank = serializers.IntegerField(read_only=True)
    rewarded_wins = serializers.IntegerField(read_only=True)
    total_earned = serializers.IntegerField(read_only=True)
    user = GameEarnerUserSerializer(source='*', read_only=True)
