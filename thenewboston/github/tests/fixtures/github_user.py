import pytest
from model_bakery import baker


@pytest.fixture
def sample_github_user(db, bucky):
    return baker.make(
        'github.GitHubUser',
        github_id='8547538',
        github_username='buckyroberts',
        reward_recipient=bucky,
    )
