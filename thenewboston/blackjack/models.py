from django.db import models

from thenewboston.general.models import CreatedModified


class BlackjackAction(CreatedModified):
    """Accepted client action identity. CasinoBet.result retains the verifiable action transcript."""

    bet = models.ForeignKey('casino.CasinoBet', on_delete=models.PROTECT)
    action_id = models.UUIDField()
    action = models.CharField(max_length=16, choices=[(action, action) for action in ('hit', 'stand', 'double')])
    expected_revision = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['bet', 'action_id'], name='blackjack_action_once'),
            models.UniqueConstraint(fields=['bet', 'expected_revision'], name='blackjack_revision_once'),
        ]
