import uuid

from django.db import models

from thenewboston.general.models import CreatedModified

from .rules import initial_board


class ReversiMatch(CreatedModified):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        FINISHED = 'finished', 'Finished'
        CANCELLED = 'cancelled', 'Cancelled'
        DECLINED = 'declined', 'Declined'
        EXPIRED = 'expired', 'Expired'

    SIDE_CHOICES = [('black', 'Black'), ('white', 'White')]

    # The creator: a member, or nobody when a signed-out visitor plays through a guest session.
    host = models.ForeignKey(
        'users.User', on_delete=models.PROTECT, related_name='reversi_as_host', null=True, blank=True
    )
    guest = models.ForeignKey(
        'users.User', on_delete=models.PROTECT, related_name='reversi_as_guest', null=True, blank=True
    )
    guest_session = models.ForeignKey('general.GuestGameSession', on_delete=models.CASCADE, null=True, blank=True)
    request_id = models.UUIDField(default=uuid.uuid4)
    mode = models.CharField(max_length=8, choices=[('computer', 'Computer'), ('human', 'Human')])
    difficulty = models.CharField(max_length=6, default='normal')
    computer_reward = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT, null=True, blank=True)
    stake_amount = models.PositiveBigIntegerField(default=0)
    prize_pool_total = models.PositiveBigIntegerField(default=0)
    settled = models.BooleanField(default=False)
    # The host's color. The guest, or the computer, plays the other one. Black moves first.
    host_side = models.CharField(max_length=5, choices=SIDE_CHOICES)
    board = models.JSONField(default=initial_board)
    active_side = models.CharField(max_length=5, choices=SIDE_CHOICES, null=True, blank=True)
    last_move = models.JSONField(null=True, blank=True)
    move_count = models.PositiveSmallIntegerField(default=0)
    time_limit_seconds = models.PositiveIntegerField(default=900)
    clock_black_ms = models.PositiveIntegerField(default=900000)
    clock_white_ms = models.PositiveIntegerField(default=900000)
    turn_started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    winner = models.CharField(max_length=5, choices=SIDE_CHOICES, null=True, blank=True)
    result_reason = models.CharField(max_length=24, blank=True)
    version = models.PositiveIntegerField(default=1)
    rematch_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_date']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(host__isnull=False, guest_session__isnull=True)
                | models.Q(host__isnull=True, guest_session__isnull=False, mode='computer', stake_amount=0),
                name='reversi_owner',
            ),
            models.UniqueConstraint(fields=['guest_session', 'request_id'], name='reversi_guest_request_once'),
            models.UniqueConstraint(fields=['host', 'request_id'], name='reversi_create_request_once'),
            models.CheckConstraint(condition=~models.Q(host=models.F('guest')), name='reversi_distinct_players'),
            models.CheckConstraint(
                condition=models.Q(mode='human', guest__isnull=False)
                | models.Q(mode='computer', guest__isnull=True, stake_amount=0),
                name='reversi_mode_players',
            ),
            models.CheckConstraint(condition=models.Q(stake_amount__lte=1000000000), name='reversi_stake_cap'),
            models.CheckConstraint(
                condition=models.Q(time_limit_seconds__in=[300, 600, 900, 1800]), name='reversi_clock'
            ),
            models.CheckConstraint(condition=models.Q(host_side__in=['black', 'white']), name='reversi_host_side'),
        ]


class ReversiLedgerEntry(CreatedModified):
    match = models.ForeignKey(ReversiMatch, on_delete=models.PROTECT, related_name='ledger_entries')
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    action = models.CharField(max_length=12, choices=[('stake', 'Stake'), ('refund', 'Refund'), ('payout', 'Payout')])
    amount = models.BigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['match', 'wallet', 'action'], name='reversi_ledger_once')]


class ReversiEvent(CreatedModified):
    match = models.ForeignKey(ReversiMatch, on_delete=models.CASCADE, related_name='events')
    version = models.PositiveIntegerField()
    event_type = models.CharField(max_length=24)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ['version']
        constraints = [models.UniqueConstraint(fields=['match', 'version'], name='reversi_event_version')]
