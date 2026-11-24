from django.db import models

from thenewboston.general.models import CreatedModified


class GameFund(CreatedModified):
    """One community TNB pool, separate from player-versus-player match escrow."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT, null=True, blank=True)
    balance = models.PositiveBigIntegerField(default=0)
    total_deposited = models.PositiveBigIntegerField(default=0)
    total_paid = models.PositiveBigIntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name='game_fund_singleton'),
            models.CheckConstraint(
                condition=models.Q(total_deposited=models.F('balance') + models.F('total_paid')),
                name='game_fund_conservation',
            ),
            models.CheckConstraint(
                condition=models.Q(total_deposited__lte=9007199254740991), name='game_fund_safe_integer'
            ),
        ]


class GameFundDeposit(CreatedModified):
    fund = models.ForeignKey(GameFund, on_delete=models.PROTECT, related_name='deposits')
    donor = models.ForeignKey('users.User', on_delete=models.PROTECT)
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT)
    request_id = models.UUIDField()
    amount = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['donor', 'request_id'], name='game_fund_deposit_once'),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0, amount__lte=1000000000), name='game_fund_deposit_limit'
            ),
        ]


class GameRewardDecision(CreatedModified):
    """A permanent decision, including unfunded wins; top-ups never replay old wins."""

    fund = models.ForeignKey(GameFund, on_delete=models.PROTECT, related_name='decisions')
    user = models.ForeignKey('users.User', on_delete=models.PROTECT)
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.PROTECT, null=True, blank=True)
    game = models.CharField(
        max_length=16, choices=[(game, game) for game in ('connect_five', 'backgammon', 'battleship')]
    )
    match_id = models.PositiveBigIntegerField()
    status = models.CharField(
        max_length=16, choices=[(status, status) for status in ('paid', 'fund_empty', 'not_eligible')]
    )
    amount = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['game', 'match_id'], name='game_reward_match_once'),
            models.CheckConstraint(
                condition=models.Q(status='paid', amount__gt=0, wallet__isnull=False)
                | models.Q(status__in=['fund_empty', 'not_eligible'], amount=0, wallet__isnull=True),
                name='game_reward_decision_amount',
            ),
        ]
