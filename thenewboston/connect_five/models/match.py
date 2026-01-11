from django.db import models
from django.utils import timezone

from thenewboston.general.models import CreatedModified

from ..constants import create_empty_board
from ..enums import MatchStatus


class ConnectFiveMatch(CreatedModified):
    challenge = models.OneToOneField(
        'connect_five.ConnectFiveChallenge',
        on_delete=models.CASCADE,
        related_name='match',
    )
    player_a = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_matches_as_player_a',
    )
    player_b = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_matches_as_player_b',
    )
    status = models.CharField(max_length=20, choices=MatchStatus.choices, default=MatchStatus.ACTIVE)
    winner = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='connect_five_matches_won',
    )
    active_player = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='connect_five_matches_active',
    )
    turn_number = models.PositiveIntegerField(default=1)
    turn_started_at = models.DateTimeField(default=timezone.now)
    clock_a_remaining_ms = models.PositiveBigIntegerField()
    clock_b_remaining_ms = models.PositiveBigIntegerField()
    prize_pool_total = models.PositiveBigIntegerField(default=0)
    max_spend_amount = models.PositiveBigIntegerField()
    time_limit_seconds = models.PositiveIntegerField()
    board_state = models.JSONField(default=create_empty_board)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f'ConnectFiveMatch {self.pk} ({self.player_a_id} vs {self.player_b_id})'
