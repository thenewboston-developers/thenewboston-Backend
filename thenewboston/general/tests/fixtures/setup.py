import pytest
from django.conf import settings
from django.test import override_settings

from thenewboston.general.advisory_locks import clear_all_advisory_locks


@pytest.fixture(autouse=True)
def unittest_settings():
    with override_settings(
        USE_ON_COMMIT_HOOK=False,
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        ACCOUNT_NUMBER=settings.ACCOUNT_NUMBER or '074463d2996f2942d8c724304fafe121f76c376ec2c35c8a2b35ebd08f226cd9',
        # The exposed signing key is used for testing only
        SIGNING_KEY=settings.SIGNING_KEY or '756eb20e5569a0c906ccb813263aa27159aeafa07d7208f860ae290c03066c51',
        DEBUG=settings.LOG_DATABASE_QUERIES,
        MEDIA_URL='http://localhost:8000/media/',
    ):
        yield


@pytest.fixture(autouse=True)
def pre_cleanup(db, unittest_settings):
    clear_all_advisory_locks()
