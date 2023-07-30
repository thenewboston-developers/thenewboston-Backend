from rest_framework import serializers

from ..models import InvitationLimit


class InvitationLimitSerializer(serializers.ModelSerializer):

    class Meta:
        model = InvitationLimit
        fields = ('owner', 'amount')
        read_only_fields = ('owner', 'amount')
