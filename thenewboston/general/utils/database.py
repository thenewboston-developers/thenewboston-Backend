from django.conf import settings
from django.db import transaction


def apply_on_commit(callable_):
    if settings.USE_ON_COMMIT_HOOK:
        transaction.on_commit(callable_)
    else:
        callable_()
