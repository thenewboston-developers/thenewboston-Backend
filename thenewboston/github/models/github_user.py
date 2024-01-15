from django.db import models

from thenewboston.general.models import CreatedModified


class GitHubUser(CreatedModified):
    github_id = models.PositiveIntegerField(unique=True)
    github_username = models.CharField(max_length=40)
    reward_recipient = models.ForeignKey('users.User', blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = 'GitHub User'
        verbose_name_plural = 'GitHub Users'

    def __str__(self):
        return f'ID: {self.pk} | GitHub ID: {self.github_id} | GitHub Username: {self.github_username}'
