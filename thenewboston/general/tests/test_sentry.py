from unittest.mock import Mock
from uuid import UUID

import jwt
import pytest
import sentry_sdk
from channels.routing import ProtocolTypeRouter
from channels.testing import HttpCommunicator
from django.core import signing
from django.core.signals import got_request_exception
from django.db import OperationalError
from rest_framework_simplejwt.authentication import JWTAuthentication
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

from thenewboston.authentication.serializers.token import TokenSerializer
from thenewboston.general.guest_games import TOKEN_SALT
from thenewboston.general.models import GuestGameSession
from thenewboston.general.tests.fixtures.sentry import get_sentry_options
from thenewboston.general.utils.sentry import hide_tokens, hide_tokens_from_sentry
from thenewboston.project.asgi import application

CLAIMS = {'token_type': 'access', 'user_id': 5}
TOKEN = jwt.encode(CLAIMS, 'not-the-secret-key', algorithm='HS256')
UNSIGNED_TOKEN = jwt.encode(CLAIMS, None, algorithm='none')
TOKEN_HEADER, TOKEN_PAYLOAD, TOKEN_SIGNATURE = TOKEN.split('.')


@pytest.mark.parametrize(
    ('value', 'expected'),
    (
        (TOKEN, '[Filtered]'),
        (UNSIGNED_TOKEN, '[Filtered]'),
        (f'Bearer {TOKEN}', 'Bearer [Filtered]'),
        (f"b'Bearer {TOKEN}'", "b'Bearer [Filtered]'"),
        (f'access_token, {TOKEN}', 'access_token, [Filtered]'),
        (f'{TOKEN} {TOKEN}', '[Filtered] [Filtered]'),
        # The way Sentry gets the variables of a stack frame, here with the ASGI scope of a request among them
        (
            {'vars': {'scope': {'headers': [["b'host'", "b'localhost'"], ["b'authorization'", f"b'Bearer {TOKEN}'"]]}}},
            {'vars': {'scope': {'headers': [["b'host'", "b'localhost'"], ["b'authorization'", '[Filtered]']]}}},
        ),
        ({TOKEN: 1}, {'[Filtered]': 1}),
        (('a', TOKEN), ['a', '[Filtered]']),
    ),
)
def test_hide_tokens(value, expected):
    assert hide_tokens(value) == expected


@pytest.mark.parametrize(
    'value',
    (
        'eyJ',
        TOKEN_HEADER,
        f'{TOKEN_HEADER}.not-a-payload.{TOKEN_SIGNATURE}',
        'thenewboston.network',
        '',
        None,
        5,
        2.5,
        True,
        {'level': 'error', 'breadcrumbs': {'values': []}, 'timestamp': 1.5},
    ),
)
def test_hide_tokens_leaves_everything_else_alone(value):
    assert hide_tokens(value) == value


def test_hide_tokens_does_not_change_the_value_it_is_given():
    event = {'vars': {'header': TOKEN}, 'frames': [TOKEN]}

    hide_tokens(event)

    assert event == {'vars': {'header': TOKEN}, 'frames': [TOKEN]}


def test_tokens_of_the_api_are_hidden(bucky):
    tokens = TokenSerializer(bucky).data

    assert hide_tokens(tokens) == {'access_token': '[Filtered]', 'refresh_token': '[Filtered]'}


def test_sentry_hides_tokens_in_events_and_transactions():
    options = get_sentry_options()

    assert options['before_send'] is hide_tokens_from_sentry
    assert options['before_send_transaction'] is hide_tokens_from_sentry


async def request_like_daphne(path, access_token=None, guest_token=None):
    # Sentry's Django integration wraps the request handler in this middleware, inside the router
    api_application = ProtocolTypeRouter({'http': SentryAsgiMiddleware(application.application_mapping['http'])})
    headers = [(b'host', b'thenewboston.network')]
    if access_token:
        headers.append((b'authorization', f'Bearer {access_token}'.encode()))
    if guest_token:
        headers.append((b'x-guest-token', guest_token.encode()))
    communicator = HttpCommunicator(api_application, 'GET', path, headers=headers)
    response = await communicator.get_response()
    await communicator.wait()

    return response


@pytest.fixture
def report_request_exceptions():
    # What Sentry's Django integration does with the exception of a request
    def report(**kwargs):
        sentry_sdk.capture_exception()

    got_request_exception.connect(report)
    yield
    got_request_exception.disconnect(report)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_token_of_request_does_not_reach_sentry(capture_sentry, bucky):
    sentry_output = capture_sentry()
    access_token = TokenSerializer.get_access_token(bucky)

    response = await request_like_daphne('/api/notifications/unread-count', access_token)

    assert response['status'] == 200
    # The transaction of the request carries the variables of every function on the stack, the router's scope with
    # the request headers among them
    assert 'channels/routing.py' in sentry_output()
    assert "b'authorization'" in sentry_output()
    assert '"[Filtered]"' in sentry_output()
    assert access_token not in sentry_output()


@pytest.mark.asyncio
@pytest.mark.usefixtures('report_request_exceptions')
async def test_token_of_failing_request_does_not_reach_sentry(capture_sentry, monkeypatch, bucky):
    sentry_output = capture_sentry()
    access_token = TokenSerializer.get_access_token(bucky)
    monkeypatch.setattr(JWTAuthentication, 'get_user', Mock(side_effect=OperationalError('connection failed')))

    response = await request_like_daphne('/api/notifications/unread-count', access_token)

    assert response['status'] == 500
    # The event of the exception carries the variables of the functions it passed through, the header and the raw
    # token in the authentication class among them
    assert 'OperationalError' in sentry_output()
    assert 'rest_framework_simplejwt/authentication.py' in sentry_output()
    assert "b'authorization'" in sentry_output()
    assert '"[Filtered]"' in sentry_output()
    assert access_token not in sentry_output()


@pytest.mark.parametrize('first_digit', '0123456789abcdef')
def test_guest_capabilities_are_hidden_in_arbitrary_copies(first_digit):
    token = signing.dumps(str(UUID(f'{first_digit}0000000-0000-0000-0000-000000000000')), salt=TOKEN_SALT)
    value = {'vars': {'signed_obj': token, 'args': [f"b'{token}'"]}}

    assert hide_tokens(value) == {'vars': {'signed_obj': '[Filtered]', 'args': ["b'[Filtered]'"]}}
    assert value['vars']['signed_obj'] == token


@pytest.mark.parametrize(
    'key',
    ['access_token', 'refresh_token', 'token', 'HTTP_X_GUEST_TOKEN', 'Authorization', "b'sec-websocket-protocol'"],
)
def test_named_credentials_and_header_pairs_are_hidden_even_when_not_recognizable_tokens(key):
    value = {'vars': {key: 'partial-or-malformed-secret', 'headers': [[key, 'partial-or-malformed-secret']]}}

    assert hide_tokens(value) == {'vars': {key: '[Filtered]', 'headers': [[key, '[Filtered]']]}}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_guest_token_of_request_does_not_reach_sentry(capture_sentry):
    session = await GuestGameSession.objects.acreate()
    token = signing.dumps(str(session.pk), salt=TOKEN_SALT)
    sentry_output = capture_sentry()

    response = await request_like_daphne('/api/checkers/matches', guest_token=token)

    assert response['status'] == 200
    assert '"transaction"' in sentry_output()
    assert 'x-guest-token' in sentry_output()
    assert token not in sentry_output()


@pytest.mark.asyncio
@pytest.mark.usefixtures('report_request_exceptions')
async def test_guest_token_of_failing_request_does_not_reach_sentry(capture_sentry, monkeypatch):
    token = signing.dumps(str(UUID('10000000-0000-0000-0000-000000000000')), salt=TOKEN_SALT)
    sentry_output = capture_sentry()
    monkeypatch.setattr(GuestGameSession.objects, 'get', Mock(side_effect=OperationalError('connection failed')))

    response = await request_like_daphne('/api/checkers/matches', guest_token=token)

    assert response['status'] == 500
    assert 'OperationalError' in sentry_output()
    assert 'general/guest_games.py' in sentry_output()
    assert token not in sentry_output()
