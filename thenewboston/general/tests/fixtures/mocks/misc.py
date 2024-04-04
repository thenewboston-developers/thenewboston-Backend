import pytest
from django.conf import settings
from django.test import override_settings


@pytest.fixture(autouse=True)
def unittest_settings():
    with override_settings(
        USE_ON_COMMIT_HOOK=False,
        CELERY_TASK_ALWAYS_EAGER=True,
        OPENAI_API_KEY=settings.OPENAI_API_KEY or 'abc123',
        PROMPTLAYER_API_KEY=settings.PROMPTLAYER_API_KEY or 'abc123',
        GITHUB_API_ACCESS_TOKEN=settings.GITHUB_API_ACCESS_TOKEN or 'abc123',
        # TODO(dmu) HIGH: Once `github-pr-assessment` template definition is fixed to use `gpt-4-turbo-preview` model
        #                 remove OPENAI_CHAT_COMPLETION_MODEL_OVERRIDE
        OPENAI_CHAT_COMPLETION_MODEL_OVERRIDE='gpt-4-turbo-preview',
    ):
        yield
