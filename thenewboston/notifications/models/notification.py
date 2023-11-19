from django.db import models

from thenewboston.general.models import CreatedModified


class Notification(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f'Notification ID: {self.pk} | Owner: {self.owner.username}'
