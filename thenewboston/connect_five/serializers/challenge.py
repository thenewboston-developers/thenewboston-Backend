from django.contrib.auth import get_user_model
from rest_framework import serializers

from thenewboston.general.serializers import BaseModelSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..constants import TIME_LIMIT_CHOICES
from ..models import ConnectFiveChallenge

User = get_user_model()


class ConnectFiveChallengeCreateSerializer(serializers.Serializer):
    opponent_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source='opponent')
    stake_amount = serializers.IntegerField(min_value=0)
    max_spend_amount = serializers.IntegerField(min_value=0)
    time_limit_seconds = serializers.IntegerField()

    def validate(self, attrs):
        request = self.context.get('request')
        opponent = attrs.get('opponent')
        if request and opponent and opponent.id == request.user.id:
            raise serializers.ValidationError({'opponent_id': 'You cannot challenge yourself.'})
        return attrs

    def validate_time_limit_seconds(self, value):
        if value not in TIME_LIMIT_CHOICES:
            raise serializers.ValidationError('Invalid time limit.')
        return value


class ConnectFiveChallengeReadSerializer(BaseModelSerializer):
    challenger = UserReadSerializer(read_only=True)
    opponent = UserReadSerializer(read_only=True)
    match_id = serializers.SerializerMethodField()

    class Meta:
        model = ConnectFiveChallenge
        fields = (
            'accepted_at',
            'challenger',
            'created_date',
            'currency',
            'expires_at',
            'id',
            'match_id',
            'max_spend_amount',
            'modified_date',
            'opponent',
            'stake_amount',
            'status',
            'time_limit_seconds',
        )

    @staticmethod
    def get_match_id(obj):
        return obj.match.id if hasattr(obj, 'match') and obj.match else None
