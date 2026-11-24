import uuid

from django.db import models

from thenewboston.general.models import CreatedModified


class DotsAndBoxesMatch(CreatedModified):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        FINISHED = 'finished', 'Finished'
        CANCELLED = 'cancelled', 'Cancelled'
        DECLINED = 'declined', 'Declined'
        EXPIRED = 'expired', 'Expired'

    # Blue creates the match and draws first; red is the invited member, or empty against the computer.
    blue = models.ForeignKey(
        'users.User', on_delete=models.PROTECT, related_name='dots_and_boxes_as_blue', null=True, blank=True
    )
    red = models.ForeignKey(
        'users.User', on_delete=models.PROTECT, related_name='dots_and_boxes_as_red', null=True, blank=True
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
    board_size = models.PositiveSmallIntegerField(default=4)
    # Per line and per box: 0 is open, 1 belongs to blue, 2 belongs to red. See rules.py for the numbering.
    lines = models.JSONField(default=list)
    boxes = models.JSONField(default=list)
    # Line numbers in the order they were drawn, so clients can replay a turn.
    moves = models.JSONField(default=list)
    score_blue = models.PositiveSmallIntegerField(default=0)
    score_red = models.PositiveSmallIntegerField(default=0)
    active_side = models.CharField(max_length=4, default='blue')
    time_limit_seconds = models.PositiveIntegerField(default=900)
    clock_blue_ms = models.PositiveIntegerField(default=900000)
    clock_red_ms = models.PositiveIntegerField(default=900000)
    turn_started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    winner = models.CharField(max_length=4, null=True, blank=True)
    result_reason = models.CharField(max_length=24, blank=True)
    version = models.PositiveIntegerField(default=1)
    rematch_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_date']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(blue__isnull=False, guest_session__isnull=True)
                | models.Q(blue__isnull=True, guest_session__isnull=False, mode='computer', stake_amount=0),
                name='dots_and_boxes_owner',
            ),
            models.UniqueConstraint(fields=['guest_session', 'request_id'], name='dots_and_boxes_guest_request_once'),
            models.UniqueConstraint(fields=['blue', 'request_id'], name='dots_and_boxes_create_request_once'),
            models.CheckConstraint(condition=~models.Q(blue=models.F('red')), name='dots_and_boxes_distinct_players'),
            models.CheckConstraint(
                condition=models.Q(mode='human', red__isnull=False)
                | models.Q(mode='computer', red__isnull=True, stake_amount=0),
                name='dots_and_boxes_mode_players',
            ),
            models.CheckConstraint(condition=models.Q(stake_amount__lte=1000000000), name='dots_and_boxes_stake_cap'),
            models.CheckConstraint(
                condition=models.Q(time_limit_seconds__in=[300, 600, 900, 1800]), name='dots_and_boxes_clock'
            ),
            models.CheckConstraint(condition=models.Q(board_size__in=[3, 4, 5]), name='dots_and_boxes_board_size'),
        ]


class DotsAndBoxesLedgerEntry(CreatedModified):
    match = models.ForeignKey(DotsAndBoxesMatch, on_delete=models.PROTECT, related_name='ledger_entries')
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    action = models.CharField(max_length=12, choices=[('stake', 'Stake'), ('refund', 'Refund'), ('payout', 'Payout')])
    amount = models.BigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['match', 'wallet', 'action'], name='dots_and_boxes_ledger_once')]


class DotsAndBoxesEvent(CreatedModified):
    match = models.ForeignKey(DotsAndBoxesMatch, on_delete=models.CASCADE, related_name='events')
    version = models.PositiveIntegerField()
    event_type = models.CharField(max_length=24)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ['version']
        constraints = [models.UniqueConstraint(fields=['match', 'version'], name='dots_and_boxes_event_version')]
