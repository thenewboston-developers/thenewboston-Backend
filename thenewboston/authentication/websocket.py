from asgiref.sync import sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.db import connections
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

ACCESS_TOKEN_SUBPROTOCOL = 'access_token'
SUBPROTOCOL_HEADER = b'sec-websocket-protocol'


def take_validated_token(scope):
    """
    Takes the access token out of the scope and returns it validated, or None and the reason.

    Sentry records the request headers and, with every event, the local variables of all functions on the stack.
    So the token is removed from the scope in place, which also removes it for the layers outside this middleware
    that hold the same scope, and it never leaves this function, which has returned before anything is awaited.
    Whatever else was offered goes too: `access_token` is the only subprotocol there is.
    """
    offered = list(scope.get('subprotocols', []))
    kept = [ACCESS_TOKEN_SUBPROTOCOL] if ACCESS_TOKEN_SUBPROTOCOL in offered else []
    scope['subprotocols'] = kept
    scope['headers'] = [
        *((name, value) for name, value in scope['headers'] if name.lower() != SUBPROTOCOL_HEADER),
        *((SUBPROTOCOL_HEADER, subprotocol.encode()) for subprotocol in kept),
    ]

    try:
        access_token = offered[offered.index(ACCESS_TOKEN_SUBPROTOCOL) + 1]
    except (ValueError, IndexError):
        return None, 'no access token'

    try:
        return JWTAuthentication().get_validated_token(access_token.encode()), None
    except AuthenticationFailed as error:
        return None, f'access token rejected ({error.detail["code"]})'


@sync_to_async(thread_sensitive=False)
def get_user(validated_token):
    """
    Applies the checks of the REST API (the user exists and is active), so that a token is accepted here exactly when
    it is accepted there.

    Not thread sensitive: all consumers share one thread for their handlers, which a database round trip for every
    connection must not hold up. Nothing closes database connections in the pool thread this runs in instead, so it
    closes its own.
    """
    try:
        return JWTAuthentication().get_user(validated_token)
    finally:
        connections.close_all()


async def authenticate(scope):
    validated_token, authentication_error = take_validated_token(scope)
    if validated_token is None:
        return AnonymousUser(), authentication_error

    try:
        return await get_user(validated_token), None
    except AuthenticationFailed as error:
        return AnonymousUser(), f'access token rejected ({error.detail["code"]})'


class AccessTokenAuthMiddleware(BaseMiddleware):
    """
    Authenticates a websocket connection with the access token of the REST API and puts the user in the scope.

    A browser cannot set headers on a websocket, so the client offers two subprotocols instead: `access_token`
    followed by the token itself. Unlike a query string, the Sec-WebSocket-Protocol header does not end up in server
    and proxy access logs.

    This must be the outermost websocket middleware, so that nothing gets to record the scope before the token is
    taken out of it (see take_validated_token).

    Nothing is rejected here. A connection without a valid token goes through as an anonymous user, the sockets open
    to everyone need no token, and the consumers that do need one decide what to do.
    """

    async def __call__(self, scope, receive, send):
        user, authentication_error = await authenticate(scope)
        scope = {**scope, 'authentication_error': authentication_error, 'user': user}

        async def send_selecting_subprotocol(message):
            # A browser fails a connection that offered subprotocols when the server selects none of them
            if message['type'] == 'websocket.accept' and message.get('subprotocol') is None:
                message = {**message, 'subprotocol': ACCESS_TOKEN_SUBPROTOCOL}

            await send(message)

        is_subprotocol_offered = ACCESS_TOKEN_SUBPROTOCOL in scope['subprotocols']
        return await self.inner(scope, receive, send_selecting_subprotocol if is_subprotocol_offered else send)
