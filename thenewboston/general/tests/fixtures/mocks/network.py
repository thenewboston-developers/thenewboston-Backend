import socket
from urllib.parse import urlparse

import pytest
from django.conf import settings

# We do not use https://pypi.org/project/pytest-network/ because we need Redis
# be available in tests, and also it looks fine to allow loopback connections,
# since they are fast and more or less safe

ALLOWED_ADDRESSES = ('127.0.0.1', '::1')

_original_connect = socket.socket.connect


class NetworkUsageException(Exception):
    pass


def resolve_domain(domain_name):
    try:
        return socket.gethostbyname(domain_name)
    except socket.gaierror:
        return None


def get_redis_hostname(url):
    return urlparse(url).hostname if url.startswith('redis://') else None


def get_dependencies_domain_names():
    domain_names = set()

    for _, value in settings.DATABASES.items():
        domain_names.add(value['HOST'])

    for _, value in settings.CHANNEL_LAYERS.items():
        if value.get('BACKEND') == 'channels_redis.core.RedisChannelLayer':
            for hostname, _ in value['CONFIG']['hosts']:
                domain_names.add(hostname)

    for redis_url in (settings.CELERY_RESULT_BACKEND, settings.CELERY_BROKER_URL):
        if redis_url and (redis_hostname := get_redis_hostname(redis_url)):
            domain_names.add(redis_hostname)

    return domain_names


def patched_connect(*args, **kwargs):
    allowed_addresses = set(ALLOWED_ADDRESSES)

    for domain_name in get_dependencies_domain_names():
        if domain_name not in allowed_addresses:  # to skip resolving 127.0.0.1
            if ip_address := resolve_domain(domain_name):
                allowed_addresses.add(ip_address)

    if len(args) >= 2 and args[1][0] in allowed_addresses:
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
