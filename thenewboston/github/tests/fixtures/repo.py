import pytest
from model_bakery import baker


@pytest.fixture
def sample_repo(db):
    return baker.make(
        'github.Repo',
        owner_name='thenewboston-developers',
        name='Core',
        contribution_branch='master',
    )
