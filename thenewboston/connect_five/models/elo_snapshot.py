from django.db import models

from thenewboston.general.models import CreatedModified


class ConnectFiveEloSnapshot(CreatedModified):
    elo = models.PositiveIntegerField()
    snapshot_date = models.DateField()
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='connect_five_elo_snapshots')

    class Meta:
        ordering = ['snapshot_date']
        verbose_name = 'Connect Five ELO snapshot'
        verbose_name_plural = 'Connect Five ELO snapshots'
        constraints = [
            models.UniqueConstraint(fields=['user', 'snapshot_date'], name='unique_connect_five_elo_snapshot'),
        ]
        indexes = [
            models.Index(fields=['user', 'snapshot_date'], name='c5_elo_snapshot_user_date_idx'),
        ]

    def __str__(self):
        return f'ConnectFiveEloSnapshot {self.pk} ({self.user_id} @ {self.snapshot_date})'
