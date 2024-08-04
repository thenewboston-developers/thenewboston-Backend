import json

from django.conf import settings
from django.db import models
from promptlayer import PromptLayer

from thenewboston.general.models import CreatedModified
from thenewboston.general.utils.misc import null_object
from thenewboston.github.client import GitHubClient

promptlayer_client = PromptLayer(api_key=settings.PROMPTLAYER_API_KEY)


class Pull(CreatedModified):
    # TODO(dmu) LOW: Consider changing to `on_delete=models.PROTECT`
    repo = models.ForeignKey('Repo', on_delete=models.CASCADE, related_name='pulls')
    issue_number = models.PositiveIntegerField()
    title = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    assessment_points = models.PositiveIntegerField(null=True, blank=True)
    assessment_explanation = models.TextField(blank=True)

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

    def fetch_diff(self):
        return GitHubClient().get_pull_request_diff(self.repo_owner_name, self.repo_name, self.issue_number)

    def assess(self, save=True):
        # All potential exceptions must be handled by the caller of the method

        metadata = {}
        tracked_user = (self.github_user or null_object).reward_recipient

        if tracked_user:
            metadata = {'user_id': str(tracked_user.id), 'username': tracked_user.username}

        response = promptlayer_client.run(
            prompt_name=settings.GITHUB_PR_ASSESSMENT_TEMPLATE_NAME,
            input_variables={'git_diff': self.fetch_diff()},
            prompt_release_label=settings.PROMPT_TEMPLATE_LABEL,
            metadata=metadata,
            tags=['github_pr_assessment']
        )

        result = response['raw_response'].choices[0].message.content
        result_json = json.loads(result)
        self.assessment_points = result_json['assessment']
        self.assessment_explanation = result_json['explanation']

        if save:
            self.save()

    def is_assessed(self):
        return self.assessment_points is not None and self.assessment_explanation
