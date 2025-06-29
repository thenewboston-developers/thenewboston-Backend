from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from thenewboston.general.constants import DEFAULT_INVITATION_LIMIT
from thenewboston.general.serializers import BaseModelSerializer
from thenewboston.general.utils.image import process_image
from thenewboston.invitations.models import Invitation, InvitationLimit

from ..validators import username_validator

User = get_user_model()


class UserReadSerializer(BaseModelSerializer):

    class Meta:
        model = User
        fields = (
            'avatar', 'bio', 'discord_username', 'facebook_username', 'github_username', 'id', 'instagram_username',
            'is_staff', 'linkedin_username', 'pinterest_username', 'reddit_username', 'tiktok_username',
            'twitch_username', 'username', 'x_username', 'youtube_username'
        )


class UserUpdateSerializer(BaseModelSerializer):

    class Meta:
        model = User
        fields = (
            'avatar', 'bio', 'discord_username', 'facebook_username', 'github_username', 'instagram_username',
            'linkedin_username', 'pinterest_username', 'reddit_username', 'tiktok_username', 'twitch_username',
            'x_username', 'youtube_username'
        )

    def update(self, instance, validated_data):
        request = self.context.get('request')

        if request and 'avatar' in request.data:
            avatar_value = request.data.get('avatar')

            if avatar_value == '':
                # User explicitly sent empty string to clear avatar
                instance.avatar.delete(save=False)
                instance.avatar = ''
                validated_data.pop('avatar', None)
            elif 'avatar' in validated_data and validated_data['avatar']:
                validated_data['avatar'] = process_image(validated_data['avatar'])

        return super().update(instance, validated_data)


class UserWriteSerializer(BaseModelSerializer):
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
        username_validator(value)

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('A user with this username already exists.')

        return value
