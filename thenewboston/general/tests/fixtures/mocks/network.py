import socket

import pytest
from django.conf import settings

# We do not use https://pypi.org/project/pytest-network/ because we need Redis
# be available in tests, and also it looks fine to allow loopback connections,
# since they are fast and more or less safe

ALLOWED_ADDRESSES = ['127.0.0.1', '::1']

_original_connect = socket.socket.connect


class NetworkUsageException(Exception):
    pass


def patched_connect(*args, **kwargs):
    if len(args) >= 2 and args[1][0] in ALLOWED_ADDRESSES:
        return _original_connect(*args, **kwargs)

    raise NetworkUsageException


if not settings.IS_CASSETTE_RECORDING:

    @pytest.fixture(autouse=True)
    def autouse_disable_network():
        # This disables network for all unittests to avoid accidental
        # creation or deletion of outside resources

        socket.socket.connect = patched_connect
        yield
        socket.socket.connect = _original_connect
