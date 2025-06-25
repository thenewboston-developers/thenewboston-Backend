import uuid
from datetime import timedelta

from django.utils import timezone

from thenewboston.exchange.models import OrderProcessingLock


def test_timestamp_adjusted_for_created_order():
    now = timezone.now()
    trade_at = now + timedelta(minutes=10)
    OrderProcessingLock.objects.create(
        id=uuid.uuid4(), acquired_at=now - timedelta(minutes=5), trade_at=trade_at, extra={}
    )
