from django.db import models

from thenewboston.general.models import CreatedModified


class ConnectFiveChatMessage(CreatedModified):
    match = models.ForeignKey(
        'connect_five.ConnectFiveMatch',
        on_delete=models.CASCADE,
        related_name='chat_messages',
    )
    sender = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_chat_messages',
    )
    message = models.TextField()

    class Meta:
        indexes = [models.Index(fields=['match', 'created_date'], name='c5_chat_match_created_idx')]
        ordering = ['-created_date']
        verbose_name = 'Connect Five chat message'
        verbose_name_plural = 'Connect Five chat messages'

    def __str__(self):
        return f'ConnectFiveChatMessage {self.pk} (match {self.match_id}, sender {self.sender_id})'
