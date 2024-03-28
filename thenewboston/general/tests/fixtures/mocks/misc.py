import pytest
from django.conf import settings
from django.test import override_settings


@pytest.fixture(autouse=True)
def on_commit_hook_mock():
    with override_settings(
        USE_ON_COMMIT_HOOK=False,
        GITHUB_API_ACCESS_TOKEN=settings.GITHUB_API_ACCESS_TOKEN or 'abc123',
    ):
        yield
