from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from thenewboston.invitations.models import Invitation

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
        instance.avatar = validated_data.get('avatar', '')
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

        invitation = Invitation.objects.filter(code=invitation_code, user__isnull=True).first()

        if not invitation:
            raise serializers.ValidationError('Invalid or used invitation code')

        user = User.objects.create_user(username=username, password=password)
        invitation.user = user
        invitation.save()

        return user
