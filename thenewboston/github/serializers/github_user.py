from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import GitHubUser


class GitHubUserSerializer(serializers.ModelSerializer):
    reward_recipient = UserReadSerializer(read_only=True)

    class Meta:
        model = GitHubUser
        fields = '__all__'
