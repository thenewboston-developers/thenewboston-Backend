import random
import string

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from thenewboston.general.constants import DEFAULT_INVITATION_LIMIT
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Invitation, InvitationLimit


class InvitationSerializer(serializers.ModelSerializer):
    recipient = UserReadSerializer(read_only=True)

    class Meta:
        model = Invitation
        fields = (
            'code',
            'created_date',
            'id',
            'modified_date',
            'note',
            'owner',
            'recipient',
        )
        read_only_fields = (
            'code',
            'created_date',
            'modified_date',
            'owner',
            'recipient',
        )

    def create(self, validated_data):
        request = self.context.get('request')
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return Invitation.objects.create(**validated_data, owner=request.user, code=code)

    def validate(self, attrs):
        request = self.context.get('request')
        invitation_limit = InvitationLimit.objects.filter(owner=request.user).first()
        max_invitations = invitation_limit.amount if invitation_limit else DEFAULT_INVITATION_LIMIT
        current_invitations = Invitation.objects.filter(owner=request.user).count()

        if current_invitations >= max_invitations:
            raise ValidationError('Invitation limit reached.')

        return attrs
