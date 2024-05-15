import pytest
from model_bakery import baker


def create_core(
    *,
    owner,
    domain='thenewboston.net',
    ticker='TNB',
):
    return baker.make(
        'cores.Core',
        domain=domain,
        owner=owner,
        ticker=ticker,
    )


@pytest.fixture
def sample_core(db, bucky):
    return create_core(
        domain='thenewboston.net',
        owner=bucky,
        ticker='TNB',
    )
