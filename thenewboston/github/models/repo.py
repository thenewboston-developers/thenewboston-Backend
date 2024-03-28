from django.db import models

from thenewboston.general.models import CreatedModified


class Repo(CreatedModified):
    # TODO(dmu) MEDIUM: Should we rather have `owner = models.ForeignKey('GitHubUser')`?
    owner_name = models.CharField(max_length=100)
    name = models.CharField(max_length=100)

    # TODO(dmu) LOW: Consider adding `is_active` field

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner_name', 'name'], name='unique_repo_owner_name_name')]

    def __str__(self):
        return f'ID: {self.pk} | Owner: {self.owner_name} | Name: {self.name}'
