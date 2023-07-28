from django.db import models
from django.utils.translation import gettext_lazy as _

from thenewboston.general.models import CreatedModified

from .item import Item


class ActivationStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active')
    DRAFT = 'DRAFT', _('Draft')


class Product(CreatedModified, Item):  # type: ignore
    activation_status = models.CharField(
        choices=ActivationStatus.choices, max_length=6, default=ActivationStatus.DRAFT
    )
    seller = models.ForeignKey('users.User', on_delete=models.CASCADE)

    def __str__(self):
        return (
            f'Product ID: {self.pk} | '
            f'Name: {self.name} | '
            f'Price: {self.price_amount} {self.price_core.ticker}'
        )
