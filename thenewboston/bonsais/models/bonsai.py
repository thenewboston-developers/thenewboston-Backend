from django.core.validators import MinValueValidator
from django.db import models

from thenewboston.general.models import CreatedModified


class Bonsai(CreatedModified):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    species = models.CharField(max_length=255, blank=True)
    genus = models.CharField(max_length=255, blank=True)
    cultivar = models.CharField(max_length=255, blank=True)
    style = models.CharField(max_length=255, blank=True)
    size = models.TextField(blank=True)
    origin = models.TextField(blank=True)
    pot = models.TextField(blank=True)
    teaser = models.CharField(max_length=500)
    description = models.TextField()
    price_amount = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    price_currency = models.ForeignKey('currencies.Currency', related_name='bonsais', on_delete=models.PROTECT)
    status = models.CharField(
        max_length=9,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
