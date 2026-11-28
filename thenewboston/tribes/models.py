from typing import ClassVar

from django.db import models


class Tournament(models.Model):
    title = models.CharField(max_length=120)
    cover_image = models.ImageField(upload_to='images/tribes/covers/', blank=True)
    max_players = models.PositiveIntegerField()
    status = models.CharField(max_length=16, default='upcoming')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    state = models.JSONField(default=dict)
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT, null=True)
    total_deposited = models.PositiveBigIntegerField(default=0)
    total_withdrawn = models.PositiveBigIntegerField(default=0)
    system_revenue = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        constraints: ClassVar[list] = [
            models.CheckConstraint(
                condition=models.Q(status__in=['upcoming', 'active', 'finished']), name='tribes_tournament_status'
            ),
            models.CheckConstraint(
                condition=models.Q(total_withdrawn__lte=models.F('total_deposited')),
                name='tribes_no_unfunded_withdrawal',
            ),
            models.CheckConstraint(
                condition=models.Q(total_deposited__lte=9007199254740991), name='tribes_safe_payments'
            ),
            models.CheckConstraint(condition=models.Q(max_players__gte=1), name='tribes_positive_capacity'),
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F('starts_at')), name='tribes_positive_duration'
            ),
        ]


class ActionReceipt(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT)
    actor = models.ForeignKey('users.User', on_delete=models.PROTECT)
    request_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    action = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=['tournament', 'actor', 'request_id'], name='tribes_action_once')
        ]


class MoneyEntry(models.Model):
    """Permanent wallet movements; positive amounts enter the tournament reserve."""

    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='money_entries')
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    amount = models.BigIntegerField()
    reason = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)


class Activity(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='activity')
    tribe_id = models.PositiveIntegerField()
    user = models.ForeignKey('users.User', on_delete=models.PROTECT, null=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class TournamentParticipant(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey('users.User', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=['tournament', 'user'], name='tribes_participant_once')
        ]
