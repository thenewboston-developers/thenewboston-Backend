from django.contrib import admin

from .models import Contribution


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'github_user_username',
        'issue_number',
        'pull_number',
        'repo_name',
        'contribution_type',
        'reward_amount',
        'created_date',
    )
    list_filter = ('contribution_type', 'repo', 'user')

    def github_user_username(self, obj):
        return obj.github_user.github_username if obj.github_user else None

    def issue_number(self, obj):
        return obj.issue.issue_number if obj.issue else None

    def pull_number(self, obj):
        return obj.pull.issue_number if obj.pull else None

    def repo_name(self, obj):
        return obj.repo.name if obj.repo else None
