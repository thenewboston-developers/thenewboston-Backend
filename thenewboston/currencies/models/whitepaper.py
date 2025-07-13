from django.db import models

from thenewboston.general.models import CreatedModified


class Whitepaper(CreatedModified):
    currency = models.OneToOneField('currencies.Currency', on_delete=models.CASCADE, related_name='whitepaper')
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    content = models.TextField()

    class Meta:
        verbose_name_plural = 'Whitepapers'

    def __str__(self):
        return f'{self.currency.ticker} Whitepaper'
