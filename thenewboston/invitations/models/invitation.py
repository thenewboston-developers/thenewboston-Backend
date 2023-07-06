from django.db import models


class Invitation(models.Model):
    code = models.CharField(max_length=6, unique=True)
    user = models.OneToOneField('users.User', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        user_string = self.user.username if self.user else '-'
        return f'{self.code} | {user_string}'
