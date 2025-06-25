import uuid

from django.db import models
from django.db.models import UniqueConstraint, Value

from thenewboston.general.models.custom_model import CustomModel


class OrderProcessingLock(CustomModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # noqa: A003
    acquired_at = models.DateTimeField(null=True, blank=True)
    trade_at = models.DateTimeField(null=True, blank=True)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [UniqueConstraint(Value(1), name='only_one_row_allowed')]
