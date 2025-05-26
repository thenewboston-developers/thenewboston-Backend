# Create your models here.
from django.db import models

from thenewboston.general.models import CreatedModified


class Currency(CreatedModified):
    CURRENCY_TYPE_CHOICES = [
        ('internal', 'Internal'),
        ('external', 'External'),
    ]
    domain = models.CharField(max_length=255, unique=True, blank=True, null=True)
    logo = models.ImageField(upload_to='images/', blank=True)
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    ticker = models.CharField(max_length=5, unique=True)
    currency_type = models.CharField(max_length=255, choices=CURRENCY_TYPE_CHOICES)

    class Meta:
        verbose_name_plural = 'Currencies'

    def __str__(self):
        return self.domain or self.ticker
