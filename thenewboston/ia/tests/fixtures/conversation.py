import pytest
from model_bakery import baker


@pytest.fixture
def sample_conversation():
    return baker.make('ia.Conversation')
