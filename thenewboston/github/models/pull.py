from django.db import models

from thenewboston.general.models import CreatedModified
from thenewboston.general.utils.misc import null_object


class Pull(CreatedModified):
    # TODO(dmu) LOW: Consider changing to `on_delete=models.PROTECT`
    repo = models.ForeignKey('Repo', on_delete=models.CASCADE, related_name='pulls')
    issue_number = models.PositiveIntegerField()
    title = models.CharField(max_length=256)

    # Potentially there may be pull requests without contributions (like low value PRs or similar),
    # more than one contribution per pull request (if there are more than one author of the PR,
    # not implemented right now) and also user is its own attribute of the pull request.
    # Also this data structure allows a more decoupled pull request syncing and processing algorithm
    # Therefore we have `github_user` field in both `Pull` and `Contribution` models.
    # TODO(dmu) LOW: Consider changing to `on_delete=models.PROTECT`
    # TODO(dmu) HIGH: Set github_user value for existing database records and make `github_user` not nullable
    github_user = models.ForeignKey('GitHubUser', on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['issue_number', 'repo'], name='unique_pull_issue_number_repo')]

    def __str__(self):
        return f'ID: {self.pk} | Issue Number: {self.issue_number} | Title: {self.title}'

    @property
    def repo_owner_name(self):
        return self.repo.owner_name

    @property
    def repo_name(self):
        return self.repo.name

    @property
    def username(self):
        return (self.github_user or null_object).github_username

    @property
    def value_points(self) -> int:
        return min(self.issue_number * 10, 1000)  # TODO(dmu) CRITICAL: Replace this with real implementation
