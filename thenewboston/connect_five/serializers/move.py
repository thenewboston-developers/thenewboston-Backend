from rest_framework import serializers

from ..enums import MoveType


class ConnectFiveMoveSerializer(serializers.Serializer):
    move_type = serializers.ChoiceField(choices=MoveType.choices)
    x = serializers.IntegerField()
    y = serializers.IntegerField()
