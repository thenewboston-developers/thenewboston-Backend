from django.db import models

from thenewboston.general.models import CreatedModified


class Repo(CreatedModified):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return f'ID: {self.pk} | Name: {self.name}'
