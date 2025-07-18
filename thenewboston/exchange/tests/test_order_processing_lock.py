import pytest

from thenewboston.exchange.models.order_processing_lock import OrderProcessingLock
from thenewboston.exchange.order_processing.engine import order_processing_lock
from thenewboston.general.exceptions import ThenewbostonRuntimeError


def test_order_processing_lock():
    assert not OrderProcessingLock.objects.exists()

    with order_processing_lock():
        lock = OrderProcessingLock.objects.get()
        assert lock.acquired_at
        assert lock.extra
        with pytest.raises(ThenewbostonRuntimeError, match='Order processing lock is already acquired at.*'):
            with order_processing_lock():
                pass

    with order_processing_lock():
        lock = OrderProcessingLock.objects.get()
        first_acquired_at = lock.acquired_at
        assert lock.acquired_at
        assert lock.extra

        with order_processing_lock(force=True):
            lock = OrderProcessingLock.objects.get()
            assert first_acquired_at < lock.acquired_at
