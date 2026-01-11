from django.db import models

from thenewboston.general.models import CreatedModified

from ..enums import MatchEventType


class ConnectFiveMatchEvent(CreatedModified):
    match = models.ForeignKey('connect_five.ConnectFiveMatch', on_delete=models.CASCADE, related_name='events')
    actor = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=32, choices=MatchEventType.choices)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ['created_date']

    def __str__(self):
        return f'ConnectFiveMatchEvent {self.pk} ({self.event_type})'
