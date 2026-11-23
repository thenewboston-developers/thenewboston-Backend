import uuid

from django.db import models

from thenewboston.general.models import CreatedModified

from .rules import initial_board


class BackgammonMatch(CreatedModified):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        BETWEEN_GAMES = 'between_games', 'Between games'
        FINISHED = 'finished', 'Finished'
        CANCELLED = 'cancelled', 'Cancelled'
        DECLINED = 'declined', 'Declined'
        EXPIRED = 'expired', 'Expired'

    white = models.ForeignKey('users.User', on_delete=models.PROTECT, related_name='backgammon_as_white')
    request_id = models.UUIDField(default=uuid.uuid4)
    black = models.ForeignKey(
        'users.User', on_delete=models.PROTECT, related_name='backgammon_as_black', null=True, blank=True
    )
    mode = models.CharField(max_length=8, choices=[('computer', 'Computer'), ('human', 'Human')])
    difficulty = models.CharField(max_length=6, default='normal')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    phase = models.CharField(max_length=16, default='finished')
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT, null=True, blank=True)
    stake_amount = models.PositiveBigIntegerField(default=0)
    prize_pool_total = models.PositiveBigIntegerField(default=0)
    settled = models.BooleanField(default=False)
    target_score = models.PositiveSmallIntegerField(default=3)
    score_white = models.PositiveSmallIntegerField(default=0)
    score_black = models.PositiveSmallIntegerField(default=0)
    game_number = models.PositiveIntegerField(default=0)
    board = models.JSONField(default=initial_board)
    active_side = models.CharField(max_length=5, default='white')
    dice = models.JSONField(default=list)
    cube_value = models.PositiveSmallIntegerField(default=1)
    cube_owner = models.CharField(max_length=5, null=True, blank=True)
    double_offered_by = models.CharField(max_length=5, null=True, blank=True)
    is_crawford = models.BooleanField(default=False)
    crawford_used = models.BooleanField(default=False)
    time_limit_seconds = models.PositiveIntegerField(default=900)
    clock_white_ms = models.PositiveIntegerField(default=900000)
    clock_black_ms = models.PositiveIntegerField(default=900000)
    turn_started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    next_game_at = models.DateTimeField(null=True, blank=True)
    winner = models.CharField(max_length=5, null=True, blank=True)
    game_winner = models.CharField(max_length=5, null=True, blank=True)
    result_points = models.PositiveSmallIntegerField(default=0)
    result_reason = models.CharField(max_length=20, blank=True)
    version = models.PositiveIntegerField(default=1)
    rematch_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_date']
        constraints = [
            models.UniqueConstraint(fields=['white', 'request_id'], name='backgammon_create_request_once'),
            models.CheckConstraint(condition=~models.Q(white=models.F('black')), name='backgammon_distinct_players'),
            models.CheckConstraint(
                condition=models.Q(mode='human', black__isnull=False)
                | models.Q(mode='computer', black__isnull=True, stake_amount=0),
                name='backgammon_mode_players',
            ),
            models.CheckConstraint(condition=models.Q(stake_amount__lte=1000000000), name='backgammon_stake_cap'),
            models.CheckConstraint(condition=models.Q(target_score__in=[1, 3, 5]), name='backgammon_target_score'),
        ]


class BackgammonLedgerEntry(CreatedModified):
    match = models.ForeignKey(BackgammonMatch, on_delete=models.PROTECT, related_name='ledger_entries')
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    action = models.CharField(max_length=12, choices=[('stake', 'Stake'), ('refund', 'Refund'), ('payout', 'Payout')])
    amount = models.BigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['match', 'wallet', 'action'], name='backgammon_ledger_once')]


class BackgammonEvent(CreatedModified):
    match = models.ForeignKey(BackgammonMatch, on_delete=models.CASCADE, related_name='events')
    version = models.PositiveIntegerField()
    event_type = models.CharField(max_length=24)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ['version']
        constraints = [models.UniqueConstraint(fields=['match', 'version'], name='backgammon_event_version')]
