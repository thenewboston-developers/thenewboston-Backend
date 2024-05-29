from django.core.files.storage import FileSystemStorage, get_storage_class
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
    core_logo = serializers.CharField(source='core__logo')
    user_avatar = serializers.SerializerMethodField('set_user_avatar')
    logo_url = serializers.SerializerMethodField('set_logo_url')
    total = serializers.IntegerField()

    def set_user_avatar(self, obj):
        media_storage = get_storage_class()()
        if not obj.get('user__avatar'):
            return None
        elif isinstance(media_storage, FileSystemStorage):
            return self.context['request'].build_absolute_uri(media_storage.url(obj.get('user__avatar')))
        return media_storage.url(obj.get('user__avatar'))

    def set_logo_url(self, obj):
        media_storage = get_storage_class()()
        if isinstance(media_storage, FileSystemStorage):
            return self.context['request'].build_absolute_uri(media_storage.url(obj.get('core__logo')))
        return media_storage.url(obj.get('core__logo'))

    class Meta:
        model = Contribution
        fields = ['user_id', 'user_username', 'user_avatar', 'core_logo', 'total', 'logo_url']
