import pytest
from django.contrib.auth import get_user_model
from model_bakery import baker

User = get_user_model()


@pytest.fixture
def bucky(db):
    user = baker.make(User, username='bucky', email='bucky@example.com')
    user.set_password('pass1234')
    user.save()
    return user
