from django.db import models

from thenewboston.general.models import CreatedModified


class ConnectFiveMatchPlayer(CreatedModified):
    match = models.ForeignKey('connect_five.ConnectFiveMatch', on_delete=models.CASCADE, related_name='players')
    user = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='connect_five_match_players', null=True, blank=True
    )
    spent_total = models.PositiveBigIntegerField(default=0)
    inventory_h2 = models.PositiveIntegerField(default=0)
    inventory_v2 = models.PositiveIntegerField(default=0)
    inventory_bomb = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['match', 'user'], name='unique_match_user'),
            models.UniqueConstraint(
                fields=['match'], condition=models.Q(user__isnull=True), name='connect_five_one_cpu_player'
            ),
        ]
        verbose_name = 'Connect Five match player'
        verbose_name_plural = 'Connect Five match players'

    def __str__(self):
        return f'ConnectFiveMatchPlayer {self.pk} ({self.user_id})'
