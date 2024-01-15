from django.db import models

from thenewboston.general.models import CreatedModified


class Contribution(CreatedModified):
    core = models.ForeignKey('cores.Core', on_delete=models.CASCADE)
    github_user = models.ForeignKey('github.GitHubUser', on_delete=models.CASCADE)
    issue = models.ForeignKey('github.Issue', on_delete=models.CASCADE)
    pull = models.ForeignKey('github.Pull', on_delete=models.CASCADE)
    repo = models.ForeignKey('github.Repo', on_delete=models.CASCADE)
    reward_amount = models.PositiveBigIntegerField()
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)

    def __str__(self):
        return f'ID: {self.pk} | Reward Amount: {self.reward_amount}'
