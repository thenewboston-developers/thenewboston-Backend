import uuid

from django.db import models
from django.utils import timezone


class AnalyticsEvent(models.Model):
    """Committed event snapshots; delivery retries retain the same ingestion UUID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=200, unique=True)
    event = models.CharField(max_length=64)
    distinct_id = models.CharField(max_length=200)
    properties = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)


class GameParticipant(models.Model):
    """Analytics identity only; never ownership, authentication, or a guest capability."""

    game = models.CharField(max_length=16)
    match_id = models.PositiveBigIntegerField()
    side = models.CharField(max_length=16)
    user_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    guest_session_id = models.UUIDField(null=True, blank=True, db_index=True)
    distinct_id = models.CharField(max_length=200, blank=True)
    session_id = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField(default=False)
    internal_traffic = models.BooleanField(default=False)
    attribution = models.JSONField(default=dict)
    started_at = models.DateTimeField(null=True, blank=True)
    engaged_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['game', 'match_id', 'side'], name='analytics_game_participant_once'),
        ]


class GameInvitationContext(models.Model):
    """Connect Five creates the match on acceptance, after the challenger leaves the request."""

    challenge_id = models.PositiveBigIntegerField(unique=True)
    identity = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
