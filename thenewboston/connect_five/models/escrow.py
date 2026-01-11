from django.db import models

from thenewboston.general.models import CreatedModified

from ..enums import EscrowStatus, LedgerAction, LedgerDirection


class ConnectFiveEscrow(CreatedModified):
    challenge = models.OneToOneField(
        'connect_five.ConnectFiveChallenge', on_delete=models.CASCADE, related_name='escrow'
    )
    currency = models.ForeignKey('currencies.Currency', on_delete=models.PROTECT)
    player_a = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_escrows_as_player_a',
    )
    player_b = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='connect_five_escrows_as_player_b',
    )
    player_a_contrib = models.PositiveBigIntegerField(default=0)
    player_b_contrib = models.PositiveBigIntegerField(default=0)
    total = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=12, choices=EscrowStatus.choices, default=EscrowStatus.LOCKED)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f'ConnectFiveEscrow {self.pk} ({self.total})'


class ConnectFiveLedgerEntry(CreatedModified):
    escrow = models.ForeignKey(
        'connect_five.ConnectFiveEscrow', on_delete=models.CASCADE, related_name='ledger_entries'
    )
    wallet = models.ForeignKey('wallets.Wallet', on_delete=models.CASCADE, related_name='connect_five_ledger_entries')
    amount = models.PositiveBigIntegerField()
    direction = models.CharField(max_length=6, choices=LedgerDirection.choices)
    action = models.CharField(max_length=32, choices=LedgerAction.choices)

    def __str__(self):
        return f'ConnectFiveLedgerEntry {self.pk} ({self.action})'
