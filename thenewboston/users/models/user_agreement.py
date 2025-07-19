from django.conf import settings
from django.db import models

from thenewboston.general.models import CreatedModified


class UserAgreement(CreatedModified):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='agreement')
    terms_agreed_at = models.DateTimeField()
    privacy_policy_agreed_at = models.DateTimeField()

    class Meta:
        db_table = 'users_useragreement'

    def __str__(self):
        return f'{self.user.username} - Agreement'
