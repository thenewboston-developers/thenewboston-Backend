import asyncio
import logging
from datetime import timedelta
from unittest.mock import Mock

import pytest
import pytest_asyncio
import sentry_sdk
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.testing import WebsocketCommunicator
from django.db import OperationalError
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

from thenewboston.authentication.serializers.token import TokenSerializer
from thenewboston.authentication.websocket import ACCESS_TOKEN_SUBPROTOCOL, AccessTokenAuthMiddleware
from thenewboston.connect_five.consumers import ConnectFiveConsumer
from thenewboston.general.consumers import authenticated_user
from thenewboston.general.enums import MessageType
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.project.asgi import application
from thenewboston.project.routing import websocket_urlpatterns
from thenewboston.wallets.consumers import WalletConsumer

pytestmark = pytest.mark.asyncio

# The token check looks the user up in a thread with a database connection of its own, so it finds a user only once
# the row is committed. That costs a flush of the database after the test, so only the tests that need it ask for it.
committed_users = pytest.mark.django_db(transaction=True)

PUBLIC_PATHS = (
    '/ws/connect-five/chat/1',
    '/ws/connect-five/public',
    '/ws/exchange-orders',
    '/ws/frontend-deployments',
    '/ws/trades',
)


def stream_notification(user):
    NotificationConsumer.stream_notification(
        message_type=MessageType.CREATE_NOTIFICATION, notification_data={'id': 1, 'owner': user.id}
    )


def stream_wallet(user):
    WalletConsumer.stream_wallet(message_type=MessageType.UPDATE_WALLET, wallet_data={'id': 1, 'owner': user.id})


def stream_match(user):
    ConnectFiveConsumer.stream_match(
        message_type=MessageType.UPDATE_CONNECT_FIVE_MATCH, match_data={'id': 1}, user_ids=[user.id]
    )


# The sockets that stream the private events of one user: path, a way to produce an event, the type of that event
PRIVATE_SOCKETS = (
    pytest.param('/ws/notifications/{user_id}', stream_notification, 'create.notification', id='notifications'),
    pytest.param('/ws/wallet/{user_id}', stream_wallet, 'update.wallet', id='wallet'),
    pytest.param('/ws/connect-five/{user_id}', stream_match, 'update.connect_five_match', id='connect-five'),
)


def get_access_token(user):
    # Issued the way the login endpoint issues it
    return TokenSerializer.get_access_token(user)


def get_expired_access_token(user):
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=-timedelta(seconds=1))
    return str(token)


def get_forged_access_token(user):
    return TokenBackend('HS256', signing_key='not-the-secret-key').encode(AccessToken.for_user(user).payload)


def get_refresh_token(user):
    return str(RefreshToken.for_user(user))


def offer(access_token):
    return [ACCESS_TOKEN_SUBPROTOCOL, access_token]


def has_group_members():
    return bool(get_channel_layer().groups)


@pytest.fixture(autouse=True)
def in_memory_channel_layer(settings):
    # Group names contain user ids, which repeat across the databases of parallel test workers that share one Redis
    settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}


@pytest.fixture
def enforcement_on(settings):
    settings.ENFORCE_WEBSOCKET_AUTHENTICATION = True


@pytest.fixture
def enforcement_off(settings):
    settings.ENFORCE_WEBSOCKET_AUTHENTICATION = False


@pytest.fixture
def authentication_log(caplog):
    caplog.set_level(logging.INFO, logger=authenticated_user.__name__)
    return lambda: [record.getMessage() for record in caplog.records if record.name == authenticated_user.__name__]


@pytest_asyncio.fixture
async def connect():
    communicators = []

    async def _connect(path, subprotocols=None, **scope):
        communicator = WebsocketCommunicator(application, path, subprotocols=subprotocols)
        # The application reads this same scope once it gets to run
        communicator.scope.update(scope)
        communicators.append(communicator)
        is_connected, subprotocol_or_close_code = await communicator.connect()
        return communicator, is_connected, subprotocol_or_close_code

    yield _connect

    for communicator in communicators:
        await communicator.disconnect()


@pytest.mark.usefixtures('enforcement_on')
class TestEnforcementOn:
    @committed_users
    @pytest.mark.parametrize(('path', 'stream', 'message_type'), PRIVATE_SOCKETS)
    async def test_user_receives_own_events(self, connect, authentication_log, bucky, path, stream, message_type):
        communicator, is_connected, subprotocol = await connect(
            path.format(user_id=bucky.id), offer(get_access_token(bucky))
        )

        assert is_connected
        # A browser fails the connection unless one of the subprotocols it offered is selected
        assert subprotocol == ACCESS_TOKEN_SUBPROTOCOL

        await sync_to_async(stream)(bucky)

        assert (await communicator.receive_json_from())['type'] == message_type
        assert authentication_log() == []

    @pytest.mark.parametrize(('path', 'stream', 'message_type'), PRIVATE_SOCKETS)
    async def test_connection_without_token_is_rejected(
        self, connect, authentication_log, bucky, path, stream, message_type
    ):
        path = path.format(user_id=bucky.id)

        communicator, is_connected, _ = await connect(path)

        assert not is_connected
        assert not has_group_members()
        await sync_to_async(stream)(bucky)
        assert await communicator.receive_nothing()
        assert authentication_log() == [f'Rejected websocket connection to {path!r}: no access token']

    @pytest.mark.parametrize(('path', 'stream', 'message_type'), PRIVATE_SOCKETS)
    async def test_connection_with_invalid_token_is_rejected(
        self, connect, authentication_log, bucky, path, stream, message_type
    ):
        path = path.format(user_id=bucky.id)

        communicator, is_connected, _ = await connect(path, offer('invalid'))

        assert not is_connected
        assert not has_group_members()
        await sync_to_async(stream)(bucky)
        assert await communicator.receive_nothing()
        assert authentication_log() == [
            f'Rejected websocket connection to {path!r}: access token rejected (token_not_valid)'
        ]

    @committed_users
    @pytest.mark.parametrize(('path', 'stream', 'message_type'), PRIVATE_SOCKETS)
    async def test_connection_with_token_of_another_user_is_rejected(
        self, connect, authentication_log, bucky, dmitry, path, stream, message_type
    ):
        path = path.format(user_id=bucky.id)

        communicator, is_connected, _ = await connect(path, offer(get_access_token(dmitry)))

        assert not is_connected
        assert not has_group_members()
        await sync_to_async(stream)(bucky)
        assert await communicator.receive_nothing()
        assert authentication_log() == [
            f'Rejected websocket connection to {path!r}: access token belongs to user {dmitry.id}'
        ]

    @pytest.mark.parametrize(
        'get_token',
        (
            pytest.param(get_expired_access_token, id='expired'),
            pytest.param(get_forged_access_token, id='signed-with-another-key'),
            pytest.param(get_refresh_token, id='refresh-token'),
        ),
    )
    async def test_token_the_rest_api_would_not_accept_is_rejected(self, connect, authentication_log, bucky, get_token):
        path = f'/ws/wallet/{bucky.id}'

        _, is_connected, _ = await connect(path, offer(get_token(bucky)))

        assert not is_connected
        assert authentication_log() == [
            f'Rejected websocket connection to {path!r}: access token rejected (token_not_valid)'
        ]

    @committed_users
    async def test_token_of_inactive_user_is_rejected(self, connect, authentication_log, bucky):
        bucky.is_active = False
        await bucky.asave()
        path = f'/ws/wallet/{bucky.id}'

        _, is_connected, _ = await connect(path, offer(get_access_token(bucky)))

        assert not is_connected
        assert authentication_log() == [
            f'Rejected websocket connection to {path!r}: access token rejected (user_inactive)'
        ]

    @committed_users
    async def test_token_of_deleted_user_is_rejected(self, connect, authentication_log, bucky):
        access_token = get_access_token(bucky)
        path = f'/ws/wallet/{bucky.id}'
        await bucky.adelete()

        _, is_connected, _ = await connect(path, offer(access_token))

        assert not is_connected
        assert authentication_log() == [
            f'Rejected websocket connection to {path!r}: access token rejected (user_not_found)'
        ]

    @pytest.mark.parametrize(
        'get_subprotocols',
        (
            pytest.param(lambda access_token: [ACCESS_TOKEN_SUBPROTOCOL], id='token-missing'),
            pytest.param(lambda access_token: [access_token], id='token-not-announced'),
            pytest.param(lambda access_token: [access_token, ACCESS_TOKEN_SUBPROTOCOL], id='token-before-announcement'),
        ),
    )
    async def test_token_must_follow_the_access_token_subprotocol(
        self, connect, authentication_log, bucky, get_subprotocols
    ):
        path = f'/ws/wallet/{bucky.id}'

        _, is_connected, _ = await connect(path, get_subprotocols(get_access_token(bucky)))

        assert not is_connected
        assert authentication_log() == [f'Rejected websocket connection to {path!r}: no access token']

    @committed_users
    async def test_user_id_in_path_must_match_exactly(self, connect, authentication_log, bucky):
        # Events go to the group of the plain id, so another spelling of the same number is nobody's socket
        path = f'/ws/wallet/0{bucky.id}'

        _, is_connected, _ = await connect(path, offer(get_access_token(bucky)))

        assert not is_connected
        assert authentication_log() == [
            f'Rejected websocket connection to {path!r}: access token belongs to user {bucky.id}'
        ]

    async def test_path_cannot_forge_a_log_line(self, connect, authentication_log, bucky):
        # Daphne takes the root path from a request header and decodes %0A, in it and in the path, to a line break
        root_path = '/\nINFO forged line\n'

        _, is_connected, _ = await connect(f'/%0AINFO forged line%0A/ws/wallet/{bucky.id}', root_path=root_path)

        assert not is_connected
        assert authentication_log() == [
            f"Rejected websocket connection to '/\\nINFO forged line\\n/ws/wallet/{bucky.id}': no access token"
        ]

    @pytest.mark.parametrize('path', PUBLIC_PATHS)
    async def test_public_socket_accepts_anonymous_connection(self, connect, authentication_log, path):
        _, is_connected, subprotocol = await connect(path)

        assert is_connected
        assert subprotocol is None
        assert authentication_log() == []

    @pytest.mark.parametrize('path', PUBLIC_PATHS)
    async def test_public_socket_accepts_connection_that_offers_invalid_token(self, connect, path):
        _, is_connected, subprotocol = await connect(path, offer('invalid'))

        assert is_connected
        assert subprotocol == ACCESS_TOKEN_SUBPROTOCOL


@pytest.mark.usefixtures('enforcement_off')
class TestEnforcementOff:
    """The explicit compatibility override keeps legacy clients working during a coordinated rollout or rollback."""

    @pytest.mark.parametrize(('path', 'stream', 'message_type'), PRIVATE_SOCKETS)
    async def test_connection_without_token_is_accepted_and_logged(
        self, connect, authentication_log, bucky, path, stream, message_type
    ):
        path = path.format(user_id=bucky.id)

        communicator, is_connected, subprotocol = await connect(path)

        assert is_connected
        assert subprotocol is None
        await sync_to_async(stream)(bucky)
        assert (await communicator.receive_json_from())['type'] == message_type
        assert authentication_log() == [
            f'Accepted unauthenticated websocket connection to {path!r}: no access token '
            '(ENFORCE_WEBSOCKET_AUTHENTICATION is off)'
        ]

    @committed_users
    async def test_connection_with_token_of_another_user_is_accepted_and_logged(
        self, connect, authentication_log, bucky, dmitry
    ):
        path = f'/ws/wallet/{bucky.id}'

        _, is_connected, subprotocol = await connect(path, offer(get_access_token(dmitry)))

        assert is_connected
        assert subprotocol == ACCESS_TOKEN_SUBPROTOCOL
        assert authentication_log() == [
            f'Accepted unauthenticated websocket connection to {path!r}: access token belongs to user {dmitry.id} '
            '(ENFORCE_WEBSOCKET_AUTHENTICATION is off)'
        ]

    @committed_users
    async def test_authenticated_connection_is_not_logged(self, connect, authentication_log, bucky):
        _, is_connected, subprotocol = await connect(f'/ws/wallet/{bucky.id}', offer(get_access_token(bucky)))

        assert is_connected
        assert subprotocol == ACCESS_TOKEN_SUBPROTOCOL
        assert authentication_log() == []

    @pytest.mark.parametrize('path', PUBLIC_PATHS)
    async def test_public_socket_accepts_anonymous_connection(self, connect, path):
        _, is_connected, _ = await connect(path)

        assert is_connected


class TestAccessTokenAuthMiddleware:
    @staticmethod
    async def run(scope, accept_message=None):
        scope = {'type': 'websocket', 'path': '/', 'headers': [], **scope}
        inner_scopes = []
        sent_messages = []

        async def inner(inner_scope, receive, send):
            inner_scopes.append(inner_scope)
            if accept_message:
                await send(accept_message)

        async def send(message):
            sent_messages.append(message)

        await AccessTokenAuthMiddleware(inner)(scope, None, send)

        return scope, inner_scopes[0], sent_messages

    @committed_users
    async def test_user_is_put_in_scope_and_token_is_taken_out(self, bucky):
        access_token = get_access_token(bucky)
        headers = [
            (b'host', b'thenewboston.network'),
            (b'sec-websocket-protocol', f'access_token, {access_token}'.encode()),
        ]

        scope, inner_scope, _ = await self.run({'headers': headers, 'subprotocols': offer(access_token)})

        assert inner_scope['user'] == bucky
        assert inner_scope['authentication_error'] is None
        assert inner_scope['subprotocols'] == [ACCESS_TOKEN_SUBPROTOCOL]
        assert inner_scope['headers'] == [
            (b'host', b'thenewboston.network'),
            (b'sec-websocket-protocol', b'access_token'),
        ]
        assert access_token not in repr(inner_scope)
        # The scope the server passed in, which the layers outside the middleware still hold
        assert access_token not in repr(scope)

    @pytest.mark.parametrize(
        ('get_subprotocols', 'kept_subprotocols', 'authentication_error'),
        (
            pytest.param(offer, [ACCESS_TOKEN_SUBPROTOCOL], 'access token rejected (token_not_valid)', id='rejected'),
            pytest.param(lambda access_token: [access_token], [], 'no access token', id='not-announced'),
            pytest.param(
                lambda access_token: [access_token, ACCESS_TOKEN_SUBPROTOCOL],
                [ACCESS_TOKEN_SUBPROTOCOL],
                'no access token',
                id='before-announcement',
            ),
            pytest.param(
                lambda access_token: [ACCESS_TOKEN_SUBPROTOCOL, '', access_token],
                [ACCESS_TOKEN_SUBPROTOCOL],
                'access token rejected (token_not_valid)',
                id='after-empty-subprotocol',
            ),
        ),
    )
    async def test_token_that_is_not_accepted_is_taken_out_of_scope_too(
        self, bucky, get_subprotocols, kept_subprotocols, authentication_error
    ):
        access_token = get_expired_access_token(bucky)
        subprotocols = get_subprotocols(access_token)
        # A server that does not lower-case header names, as it should, must not cause a leak either
        headers = [(b'Sec-WebSocket-Protocol', ', '.join(subprotocols).encode())]

        scope, inner_scope, _ = await self.run({'headers': headers, 'subprotocols': subprotocols})

        assert inner_scope['user'].is_anonymous
        assert inner_scope['authentication_error'] == authentication_error
        assert inner_scope['subprotocols'] == kept_subprotocols
        assert inner_scope['headers'] == [(b'sec-websocket-protocol', name.encode()) for name in kept_subprotocols]
        assert access_token not in repr(inner_scope)
        assert access_token not in repr(scope)

    async def test_connection_without_token_is_anonymous(self):
        _, inner_scope, _ = await self.run({})

        assert inner_scope['user'].is_anonymous
        assert inner_scope['authentication_error'] == 'no access token'

    @pytest.mark.parametrize(
        ('subprotocols', 'accept_message', 'expected_message'),
        (
            pytest.param(
                offer('invalid'),
                {'type': 'websocket.accept'},
                {'type': 'websocket.accept', 'subprotocol': ACCESS_TOKEN_SUBPROTOCOL},
                id='offered',
            ),
            pytest.param([], {'type': 'websocket.accept'}, {'type': 'websocket.accept'}, id='not-offered'),
            pytest.param(
                offer('invalid'),
                {'type': 'websocket.accept', 'subprotocol': 'other'},
                {'type': 'websocket.accept', 'subprotocol': 'other'},
                id='application-selected-another',
            ),
            pytest.param(offer('invalid'), {'type': 'websocket.close'}, {'type': 'websocket.close'}, id='rejected'),
        ),
    )
    async def test_access_token_subprotocol_is_selected_when_offered(
        self, subprotocols, accept_message, expected_message
    ):
        _, _, sent_messages = await self.run({'subprotocols': subprotocols}, accept_message)

        assert sent_messages == [expected_message]


class TestSentry:
    """
    Sentry is set up to record the request headers and, with every event, the local variables of every function on
    the stack (send_default_pii and attach_stacktrace in settings/sentry.py). The middleware must leave the access
    token in neither.
    """

    @pytest.fixture
    def sentry_output(self, capture_sentry):
        # Without the hooks that mask tokens in whatever Sentry sends: they would hide a leak in the middleware
        return capture_sentry(before_send=None, before_send_transaction=None)

    @staticmethod
    async def run_like_daphne(path, access_token, *messages):
        # The chain asgi.py builds when Sentry is configured, given the scope Daphne builds
        application = ProtocolTypeRouter(
            {'websocket': AccessTokenAuthMiddleware(SentryAsgiMiddleware(URLRouter(websocket_urlpatterns)))}
        )
        headers = [(b'sec-websocket-protocol', f'access_token, {access_token}'.encode())]
        communicator = WebsocketCommunicator(application, path, headers=headers, subprotocols=offer(access_token))

        for message in messages:
            await communicator.send_input(message)

        await asyncio.wait([communicator.future], timeout=1)

        # Daphne logs the exception an application ends with, and Sentry makes an event of every logged error. The
        # exception is taken from the task, as Daphne does: raised here, it would bring the variables of this test
        # with it.
        if exception := communicator.future.exception():
            sentry_sdk.capture_exception(exception)

    @committed_users
    async def test_connection(self, sentry_output, bucky):
        access_token = get_access_token(bucky)

        await self.run_like_daphne(
            f'/ws/wallet/{bucky.id}', access_token, {'type': 'websocket.connect'}, {'type': 'websocket.disconnect'}
        )

        # The transaction of the connection, with the variables of the middleware and of the router around it
        assert '"transaction"' in sentry_output()
        assert 'thenewboston/authentication/websocket.py' in sentry_output()
        assert 'channels/routing.py' in sentry_output()
        assert '"authentication_error"' in sentry_output()
        assert access_token not in sentry_output()

    @committed_users
    async def test_error_while_connected(self, sentry_output, bucky):
        access_token = get_access_token(bucky)

        await self.run_like_daphne(
            f'/ws/wallet/{bucky.id}',
            access_token,
            {'type': 'websocket.connect'},
            {'type': 'websocket.receive', 'text': 'not JSON'},
        )

        assert 'JSONDecodeError' in sentry_output()
        assert 'thenewboston/authentication/websocket.py' in sentry_output()
        assert access_token not in sentry_output()

    async def test_error_while_authenticating(self, sentry_output, monkeypatch, bucky):
        access_token = get_access_token(bucky)
        monkeypatch.setattr(JWTAuthentication, 'get_user', Mock(side_effect=OperationalError('connection failed')))

        await self.run_like_daphne(f'/ws/wallet/{bucky.id}', access_token, {'type': 'websocket.connect'})

        assert 'OperationalError' in sentry_output()
        assert 'thenewboston/authentication/websocket.py' in sentry_output()
        assert access_token not in sentry_output()


async def test_access_token_middleware_is_outermost():
    # Anything wrapped around it would get to record the scope before the access token is taken out of it
    assert isinstance(application.application_mapping['websocket'], AccessTokenAuthMiddleware)


async def test_unauthenticated_connections_are_visible_in_server_log(settings):
    # The `thenewboston` loggers are limited to warnings, which would hide what the rollout needs to watch
    assert settings.LOGGING['loggers'][authenticated_user.__name__]['level'] == 'INFO'


@pytest.mark.parametrize(('path', 'stream', 'message_type'), PRIVATE_SOCKETS)
async def test_private_streams_reject_unauthenticated_connections_by_default(
    connect, bucky, path, stream, message_type
):
    # No enforcement fixture: an accidental change of the application default must not expose private events.
    communicator, is_connected, _ = await connect(path.format(user_id=bucky.id))

    assert not is_connected
    assert not has_group_members()
    await sync_to_async(stream)(bucky)
    assert await communicator.receive_nothing()
