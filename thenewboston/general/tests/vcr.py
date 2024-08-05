from contextlib import contextmanager
from pathlib import Path

import vcr
from django.conf import settings

VCR_DEFAULT_KWARGS = {
    'record_mode': 'none',
    'allow_playback_repeats': True,
    'decode_compressed_response': True,
    # TODO(dmu) HIGH: promptlayer also inserts API key into request bodies. Automate the sanitization
    'filter_headers': [('Authorization', 'sanitized'), ('X-API-KEY', 'sanitized')]
}


def get_cassettes_path():
    return Path(__file__).resolve().parent / 'fixtures/cassettes'


@contextmanager
def yield_cassette(cassette_name, **kwargs):
    combined_kwargs = dict(VCR_DEFAULT_KWARGS, **kwargs)

    if settings.IS_CASSETTE_RECORDING:
        # override only if not explicitly provided in kwargs
        combined_kwargs['record_mode'] = kwargs.get('record_mode', 'once')

    path = get_cassettes_path() / cassette_name
    with vcr.use_cassette(str(path), **combined_kwargs) as cassette:
        yield cassette


@contextmanager
def assert_played(cassette, count=1):
    play_count = cassette.play_count
    yield
    if not settings.IS_CASSETTE_RECORDING and count is not None:
        played = cassette.play_count - play_count
        assert played == count, f'Expected {count}, played {played}'
