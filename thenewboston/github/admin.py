from django.contrib import admin

from .models import GitHubUser, Issue, Pull, Repo


@admin.register(GitHubUser)
class GitHubUserAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'github_id',
        'github_username',
        'reward_recipient',
    )


admin.site.register(Issue)


@admin.register(Pull)
class PullAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'repo_owner_name',
        'repo_name',
        'username',
        'issue_number',
        'title',
    )
    # TODO(dmu) MEDIUM: Improve filtering by including owner_name
    list_filter = ('repo__name', 'github_user__github_username')


@admin.register(Repo)
class RepoAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner_name', 'name', 'created_date', 'modified_date')
    list_filter = ('owner_name',)
