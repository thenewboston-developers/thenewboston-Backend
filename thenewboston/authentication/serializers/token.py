from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken


class TokenSerializer(serializers.Serializer):
    access_token = serializers.SerializerMethodField()
    refresh_token = serializers.SerializerMethodField()

    def create(self, validated_data):
        pass

    @staticmethod
    def get_access_token(user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    @staticmethod
    def get_refresh_token(user):
        refresh = RefreshToken.for_user(user)
        return str(refresh)

    def update(self, instance, validated_data):
        pass
