import pytest
from model_bakery import baker


def create_currency(*, owner, domain='thenewboston.net', ticker='TNB', **kwargs):
    return baker.make('currencies.Currency', domain=domain, owner=owner, ticker=ticker, **kwargs)


@pytest.fixture
def tnb_currency(db, bucky):
    return create_currency(domain='thenewboston.net', owner=bucky, ticker='TNB', logo='images/tnb_currency.png')


@pytest.fixture
def yyy_currency(db, bucky):
    return create_currency(domain='yyy.net', owner=bucky, ticker='YYY', logo='images/yyy_currency.png')


@pytest.fixture
def zzz_currency(db, bucky):
    return create_currency(domain='zzz.net', owner=bucky, ticker='ZZZ', logo='images/zzz_currency.png')
