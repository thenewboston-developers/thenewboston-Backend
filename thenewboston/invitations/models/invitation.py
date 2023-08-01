from django.db import models

from thenewboston.general.models import CreatedModified


class Invitation(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='invitations_created')
    recipient = models.OneToOneField(
        'users.User', on_delete=models.CASCADE, related_name='invitation_received', null=True, blank=True
    )
    code = models.CharField(max_length=6, unique=True)
    note = models.CharField(max_length=255, blank=True)

    def __str__(self):
        recipient_string = self.recipient.username if self.recipient else '-'
        return f'{self.code} | {recipient_string}'
