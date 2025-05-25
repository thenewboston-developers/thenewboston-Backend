import pytest
from model_bakery import baker


def create_currency(
    *,
    owner,
    domain='thenewboston.net',
    ticker='TNB',
):
    return baker.make(
        'currencies.Currency',
        domain=domain,
        owner=owner,
        ticker=ticker,
    )


@pytest.fixture
def sample_currency(db, bucky):
    return create_currency(
        domain='thenewboston.net',
        owner=bucky,
        ticker='TNB',
    )
