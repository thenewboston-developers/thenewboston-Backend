import pytest
from model_bakery import baker


@pytest.fixture
def tnb_mint(tnb_currency):
    baker.make('currencies.Mint', currency=tnb_currency, amount=100000)


@pytest.fixture
def yyy_mint(yyy_currency):
    baker.make('currencies.Mint', currency=yyy_currency, amount=200000)


@pytest.fixture
def zzz_mint(zzz_currency):
    baker.make('currencies.Mint', currency=zzz_currency, amount=300000)
