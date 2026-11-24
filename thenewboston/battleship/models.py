import uuid

from django.db import models

from thenewboston.general.models import CreatedModified


class BattleshipMatch(CreatedModified):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        FINISHED = 'finished', 'Finished'
        CANCELLED = 'cancelled', 'Cancelled'
        DECLINED = 'declined', 'Declined'
        EXPIRED = 'expired', 'Expired'

    host = models.ForeignKey('users.User', on_delete=models.PROTECT, related_name='battleship_as_host')
    guest = models.ForeignKey(
        'users.User', on_delete=models.PROTECT, related_name='battleship_as_guest', null=True, blank=True
    )
    request_id = models.UUIDField(default=uuid.uuid4)
    mode = models.CharField(max_length=8, choices=[('computer', 'Computer'), ('human', 'Human')])
    difficulty = models.CharField(max_length=6, default='normal')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    phase = models.CharField(max_length=16, default='finished')
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT, null=True, blank=True)
    stake_amount = models.PositiveBigIntegerField(default=0)
    prize_pool_total = models.PositiveBigIntegerField(default=0)
    settled = models.BooleanField(default=False)
    fleet_host = models.JSONField(default=list)
    fleet_guest = models.JSONField(default=list)
    shots_host = models.JSONField(default=list)
    shots_guest = models.JSONField(default=list)
    active_side = models.CharField(max_length=5, null=True, blank=True)
    time_limit_seconds = models.PositiveIntegerField(default=900)
    clock_host_ms = models.PositiveIntegerField(default=900000)
    clock_guest_ms = models.PositiveIntegerField(default=900000)
    turn_started_at = models.DateTimeField(null=True, blank=True)
    placement_deadline = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    winner = models.CharField(max_length=5, null=True, blank=True)
    result_reason = models.CharField(max_length=24, blank=True)
    last_shot = models.JSONField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    rematch_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_date']
        constraints = [
            models.UniqueConstraint(fields=['host', 'request_id'], name='battleship_create_request_once'),
            models.CheckConstraint(condition=~models.Q(host=models.F('guest')), name='battleship_distinct_players'),
            models.CheckConstraint(
                condition=models.Q(mode='human', guest__isnull=False)
                | models.Q(mode='computer', guest__isnull=True, stake_amount=0),
                name='battleship_mode_players',
            ),
            models.CheckConstraint(condition=models.Q(stake_amount__lte=1000000000), name='battleship_stake_cap'),
            models.CheckConstraint(
                condition=models.Q(time_limit_seconds__in=[300, 600, 900, 1800]), name='battleship_clock'
            ),
        ]


class BattleshipLedgerEntry(CreatedModified):
    match = models.ForeignKey(BattleshipMatch, on_delete=models.PROTECT, related_name='ledger_entries')
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    action = models.CharField(max_length=12, choices=[('stake', 'Stake'), ('refund', 'Refund'), ('payout', 'Payout')])
    amount = models.BigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['match', 'wallet', 'action'], name='battleship_ledger_once')]


class BattleshipEvent(CreatedModified):
    """Audit events never contain either player's private fleet."""

    match = models.ForeignKey(BattleshipMatch, on_delete=models.CASCADE, related_name='events')
    version = models.PositiveIntegerField()
    event_type = models.CharField(max_length=24)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ['version']
        constraints = [models.UniqueConstraint(fields=['match', 'version'], name='battleship_event_version')]
