"""Anonymous computer-game ownership; never an authenticated account."""

import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


def session_expiry():
    return timezone.now() + timedelta(days=7)


class GuestGameSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_date = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=session_expiry, db_index=True)
