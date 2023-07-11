import pytest
from model_bakery import baker


@pytest.fixture
def bucky(db):
    user = baker.make('users.User', username='bucky', email='bucky@example.com')
    user.set_password('pass1234')
    user.save()
    return user
