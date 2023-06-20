from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('id', 'username')


class UserWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(validators=[validate_password], write_only=True)

    class Meta:
        model = User
        fields = ('password', 'username')

    def create(self, validated_data):
        password = validated_data.pop('password')
        username = validated_data.get('username')
        user = User.objects.create_user(username=username, password=password)
        return user
