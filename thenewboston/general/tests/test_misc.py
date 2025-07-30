import urllib.request

import pytest

from thenewboston.general.tests.fixtures.mocks.network import NetworkUsageException


def test_network_disabled():
    with pytest.raises(NetworkUsageException):
        urllib.request.urlopen('https://google.com', timeout=0.5)
