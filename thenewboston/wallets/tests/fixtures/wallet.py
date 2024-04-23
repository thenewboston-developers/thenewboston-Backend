import pytest
from model_bakery import baker


@pytest.fixture
def sample_wallet(db, bucky, sample_core):
    return baker.make(
        'wallets.Wallet',
        balance=1_000,
        core=sample_core,
        owner=bucky,
    )
