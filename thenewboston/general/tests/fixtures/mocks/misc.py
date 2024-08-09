import pytest
from django.conf import settings
from django.test import override_settings


@pytest.fixture(autouse=True)
def unittest_settings():
    with override_settings(
        USE_ON_COMMIT_HOOK=False,
        CELERY_TASK_ALWAYS_EAGER=True,
        ACCOUNT_NUMBER=settings.ACCOUNT_NUMBER or '074463d2996f2942d8c724304fafe121f76c376ec2c35c8a2b35ebd08f226cd9',
        # The exposed signing key is used for testing only
        SIGNING_KEY=settings.SIGNING_KEY or '756eb20e5569a0c906ccb813263aa27159aeafa07d7208f860ae290c03066c51',
        OPENAI_API_KEY=settings.OPENAI_API_KEY or 'abc123',
        ANTHROPIC_API_KEY=settings.ANTHROPIC_API_KEY or 'abc123',
        PROMPTLAYER_API_KEY=settings.PROMPTLAYER_API_KEY or 'abc123',
        GITHUB_API_ACCESS_TOKEN=settings.GITHUB_API_ACCESS_TOKEN or 'abc123',
    ):
        yield
