import pytest
from model_bakery import baker


def create_github_user(reward_recipient, github_id='8547538', github_username='buckyroberts'):
    return baker.make(
        'github.GitHubUser',
        github_id=github_id,
        github_username=github_username,
        reward_recipient=reward_recipient,
    )


@pytest.fixture
def sample_github_user(db, bucky):
    return create_github_user(bucky)
