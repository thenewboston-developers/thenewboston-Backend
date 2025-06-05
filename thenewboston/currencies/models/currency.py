from django.db import models

from thenewboston.general.models import CreatedModified


class Currency(CreatedModified):
    description = models.CharField(max_length=500, null=True, blank=True)
    domain = models.CharField(max_length=255, unique=True, null=True, blank=True)
    logo = models.ImageField(upload_to='images/')
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    ticker = models.CharField(max_length=5, unique=True)

    class Meta:
        verbose_name_plural = 'Currencies'

    def __str__(self):
        return self.ticker
