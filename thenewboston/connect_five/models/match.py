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
        null=True,
        blank=True,
    )
    player_a = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_matches_as_player_a',
        null=True,
        blank=True,
    )
    player_b = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_matches_as_player_b',
        null=True,
        blank=True,
    )
    mode = models.CharField(max_length=8, choices=[('human', 'Human'), ('computer', 'Computer')], default='human')
    difficulty = models.CharField(
        max_length=6, choices=[('easy', 'Easy'), ('normal', 'Normal'), ('hard', 'Hard')], default='normal'
    )
    guest_session = models.ForeignKey('general.GuestGameSession', on_delete=models.CASCADE, null=True, blank=True)
    guest_active_side = models.CharField(
        max_length=1, choices=[('a', 'Player'), ('b', 'Computer')], null=True, blank=True
    )
    request_id = models.UUIDField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    winner_side = models.CharField(max_length=1, choices=[('a', 'Player'), ('b', 'Computer')], null=True, blank=True)
    computer_reward = models.JSONField(null=True, blank=True)
    computer_rematch_of = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='computer_rematches'
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
    player_a_elo_before = models.IntegerField(null=True, blank=True)
    player_a_elo_after = models.IntegerField(null=True, blank=True)
    player_b_elo_before = models.IntegerField(null=True, blank=True)
    player_b_elo_after = models.IntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(player_a__isnull=False, guest_session__isnull=True)
                | models.Q(
                    player_a__isnull=True,
                    guest_session__isnull=False,
                    mode='computer',
                    prize_pool_total=0,
                    max_spend_amount=0,
                ),
                name='connect_five_owner',
            ),
            models.UniqueConstraint(fields=['guest_session', 'request_id'], name='connect_five_guest_request_once'),
            models.UniqueConstraint(
                fields=['player_a', 'request_id'],
                condition=models.Q(mode='computer'),
                name='connect_five_cpu_request_once',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(mode='human', player_b__isnull=False, challenge__isnull=False)
                    | models.Q(
                        mode='computer',
                        player_b__isnull=True,
                        challenge__isnull=True,
                        request_id__isnull=False,
                        prize_pool_total=0,
                        max_spend_amount=0,
                    )
                ),
                name='connect_five_mode_players',
            ),
        ]
        ordering = ['-created_date']
        verbose_name = 'Connect Five match'
        verbose_name_plural = 'Connect Five matches'

    def __str__(self):
        return f'ConnectFiveMatch {self.pk} ({self.player_a_id} vs {self.player_b_id})'
