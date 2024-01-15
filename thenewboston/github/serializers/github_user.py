from rest_framework import serializers

from ..models import GitHubUser


class GitHubUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = GitHubUser
        fields = '__all__'
