import pytest
from model_bakery import baker


@pytest.fixture
def sample_wallet(db, bucky, sample_currency):
    return baker.make(
        'wallets.Wallet',
        balance=1_000,
        currency=sample_currency,
        owner=bucky,
    )
