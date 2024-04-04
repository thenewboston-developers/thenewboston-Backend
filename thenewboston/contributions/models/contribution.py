from django.db import models

from thenewboston.general.models import CreatedModified
from thenewboston.general.utils.misc import null_object


class Contribution(CreatedModified):
    core = models.ForeignKey('cores.Core', on_delete=models.CASCADE)
    github_user = models.ForeignKey('github.GitHubUser', on_delete=models.CASCADE)

    # TODO(dmu) LOW: Consider using GenericForeignKey instead of `issue` and `pull`
    issue = models.ForeignKey('github.Issue', on_delete=models.CASCADE, null=True, blank=True)
    pull = models.ForeignKey(
        'github.Pull',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='contributions',
    )

    # TODO(dmu) MEDIUM: `repo` can be accessed via `issue.issue` or `pull.repo`. Consider removal
    repo = models.ForeignKey('github.Repo', on_delete=models.CASCADE)
    reward_amount = models.PositiveBigIntegerField()
    # TODO(dmu) MEDIUM: users.User is navigatable through both `user` attribute and through
    #                   `github_user->reward_recipient`. Consider keeping just one of them or add a comment
    #                   describing why both should stay
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)

    @property
    def explanation(self):
        return (self.pull or null_object).assessment_explanation

    def __str__(self):
        return f'ID: {self.pk} | Reward Amount: {self.reward_amount}'
