from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from thenewboston.general.serializers import BaseModelSerializer
from thenewboston.general.utils.image import process_image

User = get_user_model()


class UserReadSerializer(BaseModelSerializer):

    class Meta:
        model = User
        fields = ('avatar', 'id', 'is_manual_contribution_allowed', 'username')


class UserUpdateSerializer(BaseModelSerializer):

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


class UserWriteSerializer(BaseModelSerializer):
    password = serializers.CharField(validators=[validate_password], write_only=True)

    class Meta:
        model = User
        fields = ('password', 'username')

    def create(self, validated_data):
        password = validated_data.pop('password')
        username = validated_data.get('username')

        user = User.objects.create_user(username=username, password=password)
        return user

    @staticmethod
    def validate_username(value):
        if not value.isalnum():
            raise serializers.ValidationError('Usernames can only contain alphanumeric characters.')

        return value
