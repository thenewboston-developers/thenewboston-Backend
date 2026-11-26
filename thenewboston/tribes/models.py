from django.db import models


class World(models.Model):
    """The singleton serializes initial creation and transitions between seasons."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='tribes_world_singleton')]


class Season(models.Model):
    status = models.CharField(max_length=16, default='recruiting')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    state = models.JSONField(default=dict)
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT, null=True)
    total_deposited = models.PositiveBigIntegerField(default=0)
    total_withdrawn = models.PositiveBigIntegerField(default=0)
    system_revenue = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['recruiting', 'active', 'finished']), name='tribes_season_status'
            ),
            models.CheckConstraint(
                condition=models.Q(total_withdrawn__lte=models.F('total_deposited')),
                name='tribes_no_unfunded_withdrawal',
            ),
            models.CheckConstraint(
                condition=models.Q(total_deposited__lte=9007199254740991), name='tribes_safe_payments'
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F('starts_at')), name='tribes_positive_duration'
            ),
        ]


class ActionReceipt(models.Model):
    season = models.ForeignKey(Season, on_delete=models.PROTECT)
    actor = models.ForeignKey('users.User', on_delete=models.PROTECT)
    request_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    action = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor', 'request_id'], name='tribes_action_once')]


class MoneyEntry(models.Model):
    """Permanent wallet movements; positive amounts enter the season reserve."""

    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='money_entries')
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    amount = models.BigIntegerField()
    reason = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)


class Activity(models.Model):
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='activity')
    tribe_id = models.PositiveIntegerField()
    user = models.ForeignKey('users.User', on_delete=models.PROTECT, null=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
