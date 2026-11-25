import base64
import hashlib
import http.client
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework_simplejwt.tokens import AccessToken

from thenewboston.authentication.websocket import ACCESS_TOKEN_SUBPROTOCOL

PUBLIC_HOST = 'thenewboston.network'
WEBSOCKET_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
PUBLIC_PATHS = (
    '/ws/connect-five/chat/0',
    '/ws/connect-five/public',
    '/ws/exchange-orders',
    '/ws/frontend-deployments',
    '/ws/trades',
)
PRIVATE_PATHS = ('/ws/notifications/{}', '/ws/wallet/{}', '/ws/connect-five/{}')


def check_handshake(path, protocols, expected_status):
    """Check the real TLS/proxy/ASGI handshake without reading or publishing any application messages."""
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    headers = {
        'Connection': 'Upgrade',
        'Upgrade': 'websocket',
        'Sec-WebSocket-Version': '13',
        'Sec-WebSocket-Key': key,
        'Origin': 'https://thenewboston.net',
    }
    if protocols:
        headers['Sec-WebSocket-Protocol'] = ', '.join(protocols)
    connection = http.client.HTTPSConnection(PUBLIC_HOST, timeout=15)
    try:
        connection.request('GET', path, headers=headers)
        response = connection.getresponse()
        if response.status != expected_status:
            raise CommandError(f'WebSocket handshake returned HTTP {response.status}; expected {expected_status}.')
        if response.status == 101:
            expected_accept = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest()).decode()
            if response.getheader('Sec-WebSocket-Accept') != expected_accept:
                raise CommandError('WebSocket handshake has an invalid Sec-WebSocket-Accept header.')
            selected = response.getheader('Sec-WebSocket-Protocol')
            expected_protocol = ACCESS_TOKEN_SUBPROTOCOL if protocols else None
            if selected != expected_protocol:
                raise CommandError('The proxy/server did not negotiate the expected WebSocket subprotocol.')
    except (OSError, http.client.HTTPException) as error:
        # Do not include request headers, credentials, or exception representations in deployment logs.
        raise CommandError(f'WebSocket connection failed ({type(error).__name__}).') from None
    finally:
        connection.close()


class Command(BaseCommand):
    help = 'Verify production public/private WebSocket handshakes through TLS and nginx without publishing data.'

    def add_arguments(self, parser):
        parser.add_argument('--expect-enforcement', choices=('on', 'off'))

    def handle(self, *args, **options):
        enforced = settings.ENFORCE_WEBSOCKET_AUTHENTICATION
        expected = options.get('expect_enforcement')
        if expected is not None and enforced != (expected == 'on'):
            raise CommandError(f'WebSocket enforcement setting does not match expected mode {expected}.')
        user = get_user_model().objects.filter(is_active=True).order_by('pk').first()
        if user is None:
            raise CommandError('An active account is required for the authenticated handshake check.')

        rejected_status = 403 if enforced else 101
        for path in PUBLIC_PATHS:
            check_handshake(path, [], 101)
            check_handshake(path, [ACCESS_TOKEN_SUBPROTOCOL], 101)
        for path in PRIVATE_PATHS:
            # Mint just before the authenticated check: slow public handshakes must not consume its lifetime.
            # This credential exists only in this process and expires after one minute; never print or persist it.
            token = AccessToken.for_user(user)
            token.set_exp(lifetime=timedelta(seconds=60))
            protocols = [ACCESS_TOKEN_SUBPROTOCOL, str(token)]
            check_handshake(path.format(user.pk), protocols, 101)
            check_handshake(path.format(user.pk), [], rejected_status)
            check_handshake(path.format(user.pk), [ACCESS_TOKEN_SUBPROTOCOL, 'invalid'], rejected_status)
            # No real account uses ID 0: this checks ownership without subscribing to a second user's updates.
            check_handshake(path.format(0), protocols, rejected_status)
        mode = 'enforced' if enforced else 'compatibility'
        self.stdout.write(
            self.style.SUCCESS(f'WebSocket authentication verified: {mode}; 22 public/private handshakes.')
        )
