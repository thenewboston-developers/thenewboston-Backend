from django.db import models

from thenewboston.general.models import CreatedModified


class Mint(CreatedModified):
    currency = models.ForeignKey('currencies.Currency', on_delete=models.CASCADE, related_name='mints')
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    amount = models.PositiveBigIntegerField()

    def __str__(self):
        return f'Mint {self.amount} {self.currency.ticker} by {self.owner.username}'
