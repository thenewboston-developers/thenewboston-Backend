from django.db import models
from django.utils.translation import gettext_lazy as _

from thenewboston.general.models import CreatedModified


class SenderType(models.TextChoices):
    IA = 'IA', _('Ia')
    USER = 'USER', _('User')


class Message(CreatedModified):
    conversation = models.ForeignKey('ia.Conversation', on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey('users.User', blank=True, null=True, on_delete=models.CASCADE)
    sender_type = models.CharField(choices=SenderType.choices, max_length=4, default=SenderType.USER)
    text = models.TextField()

    def __str__(self):
        return f'Message ID: {self.pk}'
