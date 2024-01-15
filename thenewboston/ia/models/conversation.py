from django.db import models

from thenewboston.general.models import CreatedModified


class Conversation(CreatedModified):
    name = models.CharField(max_length=200)
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)

    def __str__(self):
        return f'Conversation ID: {self.pk} | ' f'Name: {self.name}'
