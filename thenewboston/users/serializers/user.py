from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from thenewboston.general.constants import DEFAULT_INVITATION_LIMIT
from thenewboston.general.utils.image import process_image
from thenewboston.invitations.models import Invitation, InvitationLimit

User = get_user_model()


class UserReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('avatar', 'id', 'username')


class UserUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('avatar',)

    def update(self, instance, validated_data):
        avatar = validated_data.get('avatar')

        if avatar:
            file = process_image(avatar)
            instance.avatar = file
        else:
            instance.avatar = ''

        instance.save()
        return instance


class UserWriteSerializer(serializers.ModelSerializer):
    invitation_code = serializers.CharField(write_only=True)
    password = serializers.CharField(validators=[validate_password], write_only=True)

    class Meta:
        model = User
        fields = ('invitation_code', 'password', 'username')

    def create(self, validated_data):
        invitation_code = validated_data.pop('invitation_code')
        password = validated_data.pop('password')
        username = validated_data.get('username')

        invitation = Invitation.objects.filter(code=invitation_code, recipient__isnull=True).first()

        if not invitation:
            raise serializers.ValidationError('Invalid or used invitation code')

        user = User.objects.create_user(username=username, password=password)
        invitation.recipient = user
        invitation.save()
        inviter_limit = InvitationLimit.objects.filter(owner=invitation.owner).first()

        if inviter_limit:
            recipient_limit = max(inviter_limit.amount - 1, 0)
        else:
            recipient_limit = DEFAULT_INVITATION_LIMIT - 1

        InvitationLimit.objects.create(owner=user, amount=recipient_limit)

        return user

    @staticmethod
    def validate_username(value):
        if not value.isalnum():
            raise serializers.ValidationError('Usernames can only contain alphanumeric characters.')

        return value
