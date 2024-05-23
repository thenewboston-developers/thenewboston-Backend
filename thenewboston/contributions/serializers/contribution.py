from rest_framework import serializers

from thenewboston.cores.serializers.core import CoreReadSerializer
from thenewboston.github.serializers.github_user import GitHubUserSerializer
from thenewboston.github.serializers.issue import IssueSerializer
from thenewboston.github.serializers.pull import PullSerializer
from thenewboston.github.serializers.repo import RepoSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Contribution


class ContributionSerializer(serializers.ModelSerializer):
    core = CoreReadSerializer(read_only=True)
    github_user = GitHubUserSerializer(read_only=True)
    issue = IssueSerializer(read_only=True)
    pull = PullSerializer(read_only=True)
    repo = RepoSerializer(read_only=True)
    user = UserReadSerializer(read_only=True)

    class Meta:
        model = Contribution
        fields = '__all__'


class TopContributionSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField()
    user_username = serializers.CharField(source='user__username')
    user_avatar = serializers.CharField(source='user__avatar')
    core_logo = serializers.CharField(source='core__logo')
    total = serializers.IntegerField()

    class Meta:
        model = Contribution
        fields = ['user_id', 'user_username', 'user_avatar', 'core_logo', 'total']
