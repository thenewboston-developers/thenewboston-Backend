from rest_framework import serializers

from .move import ConnectFiveMoveSerializer
from ..constants import BOARD_SIZE, TIME_LIMIT_CHOICES


class ConnectFiveComputerCreateSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    difficulty = serializers.ChoiceField(choices=['easy', 'normal', 'hard'], default='normal')
    time_limit_seconds = serializers.ChoiceField(choices=TIME_LIMIT_CHOICES, default=900)
    rematch_of = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError('Computer matches are free and do not accept stake or purchase settings.')
        return attrs


class ConnectFiveComputerActionSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class ConnectFiveComputerMoveSerializer(ConnectFiveMoveSerializer, ConnectFiveComputerActionSerializer):
    x = serializers.IntegerField(min_value=0, max_value=BOARD_SIZE - 1)
    y = serializers.IntegerField(min_value=0, max_value=BOARD_SIZE - 1)
