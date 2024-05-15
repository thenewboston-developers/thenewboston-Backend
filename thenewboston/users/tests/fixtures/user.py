import pytest
from model_bakery import baker


@pytest.fixture
def bucky(db):
    return baker.make(
        'users.User',
        username='bucky',
        email='bucky@example.com',
        is_manual_contribution_allowed=True,
        manual_contribution_reward_daily_limit=1000,
        # The hash stands for: pass1234
        # Using hash makes tests much faster
        password='pbkdf2_sha256$600000$xtoVMXq0IfPVEH9OUp5zsL$QCNMq3hD+3vRP641TsIilSmOf4agkjOx/VHTbH6nU0o='
    )


@pytest.fixture
def ia_user(db):
    return baker.make('users.User', username='ia')
