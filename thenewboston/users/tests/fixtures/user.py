import pytest
from model_bakery import baker


@pytest.fixture
def bucky(db):
    user = baker.make('users.User', username='bucky', email='bucky@example.com')
    # TODO(dmu) MEDIUM: Settings password like this may significantly slow unittests down. Consider assigning
    #                   password hash directly instead
    user.set_password('pass1234')
    user.save()
    return user


@pytest.fixture
def ia_user(db):
    return baker.make('users.User', username='ia')
