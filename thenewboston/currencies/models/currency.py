from django.db import models
from django.db.models import Sum

from thenewboston.general.models import CreatedModified, SocialMediaMixin

from .mint import Mint


def get_total_amount_minted(currency_id):
    # So we do not have to select `Currency` just to get the total amount minted
    return Mint.objects.filter(currency_id=currency_id).aggregate(total=Sum('amount'))['total'] or 0


class Currency(CreatedModified, SocialMediaMixin):
    description = models.CharField(max_length=500, null=True, blank=True)
    domain = models.CharField(max_length=255, unique=True, null=True, blank=True)
    logo = models.ImageField(upload_to='images/')
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    ticker = models.CharField(max_length=5, unique=True)

    class Meta:
        verbose_name_plural = 'Currencies'

    def __str__(self):
        return self.ticker

    def get_total_amount_minted(self):
        return get_total_amount_minted(self.id)
