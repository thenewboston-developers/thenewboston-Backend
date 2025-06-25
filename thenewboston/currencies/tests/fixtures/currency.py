import pytest
from model_bakery import baker


def create_currency(*, owner, domain='thenewboston.net', ticker='TNB'):
    return baker.make('currencies.Currency', domain=domain, owner=owner, ticker=ticker)


@pytest.fixture
def tnb_currency(db, bucky):
    return create_currency(domain='thenewboston.net', owner=bucky, ticker='TNB')


@pytest.fixture
def yyy_currency(db, bucky):
    return create_currency(domain='yyy.net', owner=bucky, ticker='YYY')


@pytest.fixture
def zzz_currency(db, bucky):
    return create_currency(domain='zzz.net', owner=bucky, ticker='ZZZ')
