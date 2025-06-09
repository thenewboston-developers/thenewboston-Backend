from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer


class TransferSerializer(serializers.Serializer):
    post_id = serializers.IntegerField(allow_null=True)
    comment_id = serializers.IntegerField(allow_null=True)
    amount = serializers.IntegerField()
    currency = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
    content = serializers.CharField()
    counterparty = UserReadSerializer()
