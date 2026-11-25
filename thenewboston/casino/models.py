import uuid

from django.db import models

from thenewboston.general.models import CreatedModified

MAX_SAFE_INTEGER = 9007199254740991


class CasinoFund(CreatedModified):
    """Casino treasury only. Accepted stakes are included in balance and protected by reserved."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT, null=True, blank=True)
    balance = models.PositiveBigIntegerField(default=0)
    reserved = models.PositiveBigIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    risk_limit_bps = models.PositiveSmallIntegerField(default=100)

    @property
    def available(self):
        return self.balance - self.reserved

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name='casino_fund_singleton'),
            models.CheckConstraint(condition=models.Q(reserved__lte=models.F('balance')), name='casino_fund_covered'),
            models.CheckConstraint(condition=models.Q(balance__lte=MAX_SAFE_INTEGER), name='casino_fund_safe_integer'),
            models.CheckConstraint(
                condition=models.Q(risk_limit_bps__gte=1, risk_limit_bps__lte=10000), name='casino_fund_risk_range'
            ),
        ]


class CasinoGameConfig(CreatedModified):
    game = models.CharField(max_length=32, primary_key=True)
    enabled = models.BooleanField(default=True)
    rules_version = models.PositiveSmallIntegerField(default=1)
    min_bet = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(min_bet__gte=1, min_bet__lte=1000000000), name='casino_min_bet_range'
            ),
        ]


class CasinoCommitment(CreatedModified):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.User', on_delete=models.PROTECT)
    server_seed_hash = models.CharField(max_length=64)
    encrypted_server_seed = models.TextField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'used_at', 'expires_at'], name='casino_pending_commitment')]


class CasinoBet(CreatedModified):
    fund = models.ForeignKey(CasinoFund, on_delete=models.PROTECT)
    user = models.ForeignKey('users.User', on_delete=models.PROTECT)
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    request_id = models.UUIDField()
    request_fingerprint = models.CharField(max_length=64)
    game = models.CharField(max_length=32)
    rules_version = models.PositiveSmallIntegerField()
    amount = models.PositiveBigIntegerField()
    total_stake = models.PositiveBigIntegerField()
    house_exposure = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, choices=[('open', 'Open'), ('settled', 'Settled')], default='open')
    selection = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    payout = models.PositiveBigIntegerField(default=0)
    settlement_reason = models.CharField(max_length=32, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    commitment = models.OneToOneField(CasinoCommitment, on_delete=models.PROTECT)
    client_seed = models.CharField(max_length=128)
    revealed_server_seed = models.CharField(max_length=64, blank=True)

    @property
    def protected_amount(self):
        return self.total_stake + self.house_exposure if self.status == 'open' else 0

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'request_id'], name='casino_bet_request_once'),
            models.UniqueConstraint(fields=['user'], condition=models.Q(status='open'), name='casino_one_open_bet'),
            models.CheckConstraint(condition=models.Q(amount__gte=1), name='casino_bet_positive_stake'),
            models.CheckConstraint(
                condition=models.Q(total_stake__gte=models.F('amount')), name='casino_bet_total_stake'
            ),
            models.CheckConstraint(
                condition=models.Q(
                    total_stake__lte=MAX_SAFE_INTEGER,
                    house_exposure__lte=MAX_SAFE_INTEGER,
                    payout__lte=MAX_SAFE_INTEGER,
                ),
                name='casino_bet_safe_integer',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status='open', settled_at__isnull=True, settlement_reason='', payout=0, revealed_server_seed=''
                )
                | (
                    models.Q(status='settled', settled_at__isnull=False)
                    & ~models.Q(settlement_reason='')
                    & ~models.Q(revealed_server_seed='')
                ),
                name='casino_bet_settlement_state',
            ),
            models.CheckConstraint(
                condition=models.Q(payout__lte=models.F('total_stake') + models.F('house_exposure')),
                name='casino_bet_payout_covered',
            ),
        ]
        indexes = [models.Index(fields=['user', '-created_date'], name='casino_user_history')]


class CasinoLedgerEntry(CreatedModified):
    """Append-only transfer record. Payout includes returned stakes; zero payouts have a receipt too."""

    fund = models.ForeignKey(CasinoFund, on_delete=models.PROTECT)
    user = models.ForeignKey('users.User', on_delete=models.PROTECT)
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    bet = models.ForeignKey(CasinoBet, on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(
        max_length=16, choices=[(value, value) for value in ('deposit', 'withdrawal', 'stake', 'payout')]
    )
    amount = models.PositiveBigIntegerField()
    request_id = models.UUIDField(null=True, blank=True)
    event_key = models.CharField(max_length=128, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'request_id'], name='casino_admin_transfer_once'),
            models.UniqueConstraint(fields=['bet', 'event_key'], name='casino_bet_event_once'),
            models.UniqueConstraint(fields=['bet'], condition=models.Q(kind='payout'), name='casino_payout_once'),
            models.CheckConstraint(condition=models.Q(amount__lte=MAX_SAFE_INTEGER), name='casino_ledger_safe_integer'),
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=['deposit', 'withdrawal'], bet__isnull=True, request_id__isnull=False, amount__gt=0
                )
                | models.Q(kind='stake', bet__isnull=False, request_id__isnull=True, amount__gt=0)
                | models.Q(kind='payout', bet__isnull=False, request_id__isnull=True),
                name='casino_ledger_kind_fields',
            ),
            models.CheckConstraint(
                condition=models.Q(bet__isnull=True, event_key='')
                | (models.Q(bet__isnull=False) & ~models.Q(event_key='')),
                name='casino_ledger_event_key',
            ),
        ]
