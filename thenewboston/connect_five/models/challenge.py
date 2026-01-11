from django.db import models

from thenewboston.general.models import CreatedModified

from ..enums import ChallengeStatus


class ConnectFiveChallenge(CreatedModified):
    challenger = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_challenges_sent',
    )
    opponent = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_challenges_received',
    )
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT)
    stake_amount = models.PositiveBigIntegerField()
    max_spend_amount = models.PositiveBigIntegerField()
    time_limit_seconds = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=ChallengeStatus.choices, default=ChallengeStatus.PENDING)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f'ConnectFiveChallenge {self.pk} ({self.challenger_id} vs {self.opponent_id})'
