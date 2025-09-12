import pytest
from model_bakery import baker


@pytest.fixture
def bucky(db):
    return baker.make(
        'users.User',
        username='bucky',
        email='bucky@example.com',
        # The hash stands for: pass1234
        # Using hash makes tests much faster
        password='pbkdf2_sha256$600000$xtoVMXq0IfPVEH9OUp5zsL$QCNMq3hD+3vRP641TsIilSmOf4agkjOx/VHTbH6nU0o=',
    )


@pytest.fixture
def dmitry(db):
    return baker.make(
        'users.User',
        username='dmitry',
        email='dmitry@example.com',
        # The hash stands for: pass1234
        # Using hash makes tests much faster
        password='pbkdf2_sha256$600000$xtoVMXq0IfPVEH9OUp5zsL$QCNMq3hD+3vRP641TsIilSmOf4agkjOx/VHTbH6nU0o=',
    )


@pytest.fixture
def sample_search_users(db):
    """Create sample users for search testing."""
    users = [
        baker.make('users.User', username='alice'),
        baker.make('users.User', username='bob'),
        baker.make('users.User', username='charlie'),
        baker.make('users.User', username='david'),
        baker.make('users.User', username='eve'),
        baker.make('users.User', username='frank'),
        baker.make('users.User', username='grace'),
        baker.make('users.User', username='henry'),
        baker.make('users.User', username='iris'),
        baker.make('users.User', username='jack'),
        baker.make('users.User', username='AliceWonder'),
        baker.make('users.User', username='ALICE_CAPS'),
    ]
    return users
