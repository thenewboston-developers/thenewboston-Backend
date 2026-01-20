from django.db import models

from thenewboston.general.models import CreatedModified

from ..constants import ELO_STARTING_SCORE


class ConnectFiveStats(CreatedModified):
    user = models.OneToOneField('users.User', on_delete=models.CASCADE, related_name='connect_five_stats')
    elo = models.PositiveIntegerField(default=ELO_STARTING_SCORE)
    matches_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    draws = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Connect Five stats'
        verbose_name_plural = 'Connect Five stats'

    def __str__(self):
        return f'ConnectFiveStats {self.pk} ({self.user_id})'
