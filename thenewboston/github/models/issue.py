from django.db import models

from thenewboston.general.models import CreatedModified


class Issue(CreatedModified):
    repo = models.ForeignKey('Repo', on_delete=models.CASCADE)
    issue_number = models.PositiveIntegerField()
    title = models.CharField(max_length=256)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['issue_number', 'repo'], name='unique_issue_issue_number_repo')]

    def __str__(self):
        return f'ID: {self.pk} | Issue Number: {self.issue_number} | Title: {self.title}'
