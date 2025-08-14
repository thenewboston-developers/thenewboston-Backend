from rest_framework import serializers

from ..models import InvitationLimit


class InvitationLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvitationLimit
        fields = ('amount', 'id', 'owner')
        read_only_fields = ('amount', 'id', 'owner')
