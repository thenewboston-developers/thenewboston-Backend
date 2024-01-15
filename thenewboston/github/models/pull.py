from django.db import models

from thenewboston.general.models import CreatedModified


class Pull(CreatedModified):
    issue_id = models.PositiveIntegerField(unique=True)
    repo = models.ForeignKey('github.Repo', on_delete=models.CASCADE)
    title = models.CharField(max_length=256)

    def __str__(self):
        return f'ID: {self.pk} | Issue ID: {self.issue_id} | Title: {self.title}'
