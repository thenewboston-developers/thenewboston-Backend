import pytest
from model_bakery import baker


@pytest.fixture
def bucky_tnb_wallet(db, bucky, tnb_currency):
    return baker.make('wallets.Wallet', balance=1_000, currency=tnb_currency, owner=bucky)


@pytest.fixture
def dmitry_tnb_wallet(db, dmitry, tnb_currency):
    return baker.make('wallets.Wallet', balance=1_000, currency=tnb_currency, owner=dmitry)


@pytest.fixture
def bucky_yyy_wallet(db, bucky, yyy_currency):
    return baker.make('wallets.Wallet', balance=1_000, currency=yyy_currency, owner=bucky)


@pytest.fixture
def dmitry_yyy_wallet(db, dmitry, yyy_currency):
    return baker.make('wallets.Wallet', balance=1_000, currency=yyy_currency, owner=dmitry)


@pytest.fixture
def bucky_zzz_wallet(db, bucky, zzz_currency):
    return baker.make('wallets.Wallet', balance=1_000, currency=zzz_currency, owner=bucky)


@pytest.fixture
def dmitry_zzz_wallet(db, dmitry, zzz_currency):
    return baker.make('wallets.Wallet', balance=1_000, currency=zzz_currency, owner=dmitry)
