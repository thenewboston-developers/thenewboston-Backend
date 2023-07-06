from django.db import models
from django.utils.crypto import get_random_string


class Invitation(models.Model):
    code = models.CharField(max_length=6, unique=True, default=get_random_string(6))
    user = models.OneToOneField('users.User', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        user_string = self.user.username if self.user else '-'
        return f'{self.code} | {user_string}'
