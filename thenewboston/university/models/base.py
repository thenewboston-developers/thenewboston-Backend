from django.db import models
from django.utils.translation import gettext_lazy as _

from thenewboston.general.models import CreatedModified


class PublicationStatus(models.TextChoices):
    DRAFT = 'DRAFT', _('Draft')
    PUBLISHED = 'PUBLISHED', _('Published')


class Base(CreatedModified):
    name = models.CharField(max_length=1024)
    description = models.TextField(blank=True, null=True)
    publication_status = models.CharField(
        choices=PublicationStatus.choices, max_length=10, default=PublicationStatus.DRAFT
    )

    class Meta:
        abstract = True
