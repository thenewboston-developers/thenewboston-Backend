import pytest
from model_bakery import baker


def create_repo(
    owner_name='thenewboston-developers',
    name='Core',
    contribution_branch='master',
):
    return baker.make(
        'github.Repo',
        owner_name=owner_name,
        name=name,
        contribution_branch=contribution_branch,
    )


@pytest.fixture
def sample_repo(db):
    return create_repo()
