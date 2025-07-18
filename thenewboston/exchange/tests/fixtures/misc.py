import pytest

from thenewboston.exchange.order_processing.engine import order_processing_lock


@pytest.fixture
def lock_order_processing():
    with order_processing_lock(force=True):
        yield
