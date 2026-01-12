from rest_framework import serializers

from ..enums import SpecialType


class ConnectFivePurchaseSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(default=1, min_value=1, required=False)
    special_type = serializers.ChoiceField(choices=SpecialType.choices)
