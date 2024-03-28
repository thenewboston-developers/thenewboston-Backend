import pytest
from model_bakery import baker


@pytest.fixture
def sample_core(db, bucky):
    return baker.make(
        'cores.Core',
        domain='thenewboston.net',
        owner=bucky,
        ticker='TNB',
    )
