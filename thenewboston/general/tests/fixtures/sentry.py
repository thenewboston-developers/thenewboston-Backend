import runpy
from pathlib import Path
from unittest import mock

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

SENTRY_SETTINGS_PATH = Path(__file__).resolve().parents[3] / 'project' / 'settings' / 'sentry.py'


def get_sentry_options():
    """Returns the options settings/sentry.py hands to Sentry when a DSN is configured."""
    with mock.patch('sentry_sdk.init') as init:
        runpy.run_path(
            str(SENTRY_SETTINGS_PATH),
            init_globals={
                'ENV_NAME': 'unittests',
                'SENTRY_DSN': 'http://public@127.0.0.1:9/1',
                'SENTRY_EVENT_LEVEL': 'WARNING',
                'SENTRY_TRACES_SAMPLE_RATE': 1.0,
            },
        )

    return init.call_args.kwargs


@pytest.fixture
def capture_sentry():
    """
    Returns a function that makes Sentry record with the options of settings/sentry.py, apart from those passed to
    it, and that returns a function giving everything Sentry would have sent so far. Nothing is sent anywhere.
    """
    clients = []

    def _capture_sentry(**options):
        envelopes = []

        class CollectingTransport(Transport):
            def capture_envelope(self, envelope):
                envelopes.append(envelope)

        client = sentry_sdk.Client(
            **{
                **get_sentry_options(),
                # The integrations patch Django and logging for good, and do not decide how much an event carries
                'default_integrations': False,
                'integrations': [],
                'transport': CollectingTransport,
                **options,
            }
        )
        clients.append(client)
        # Applications under test run in a context of their own, where only the client of the global scope is seen
        sentry_sdk.get_global_scope().set_client(client)

        return lambda: b''.join(item.get_bytes() for envelope in envelopes for item in envelope.items).decode()

    yield _capture_sentry

    sentry_sdk.get_global_scope().set_client(None)
    for client in clients:
        client.close()
