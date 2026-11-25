import base64
import hashlib
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework_simplejwt.tokens import AccessToken

from thenewboston.general.management.commands import (
    announce_frontend_deployment as announcement,
    verify_websocket_authentication as verification,
)
from thenewboston.general.models import FrontendDeployment


@pytest.fixture
def connection(monkeypatch):
    connection = Mock()
    response = connection.getresponse.return_value
    response.status = 101

    def get_header(name):
        headers = connection.request.call_args.kwargs['headers']
        if name == 'Sec-WebSocket-Accept':
            source = headers['Sec-WebSocket-Key'] + verification.WEBSOCKET_GUID
            return base64.b64encode(hashlib.sha1(source.encode()).digest()).decode()
        if name == 'Sec-WebSocket-Protocol' and 'Sec-WebSocket-Protocol' in headers:
            return 'access_token'
        return None

    response.getheader.side_effect = get_header
    factory = Mock(return_value=connection)
    monkeypatch.setattr(verification.http.client, 'HTTPSConnection', factory)
    return connection


@pytest.mark.parametrize('protocols', ([], ['access_token'], ['access_token', 'synthetic-token']))
def test_handshake_checks_real_protocol_and_closes_connection(connection, protocols):
    verification.check_handshake('/ws/trades', protocols, 101)

    verification.http.client.HTTPSConnection.assert_called_once_with(verification.PUBLIC_HOST, timeout=15)
    assert connection.request.call_args.args == ('GET', '/ws/trades')
    headers = connection.request.call_args.kwargs['headers']
    assert headers['Origin'] == 'https://thenewboston.net'
    assert headers.get('Sec-WebSocket-Protocol') == (', '.join(protocols) if protocols else None)
    connection.close.assert_called_once()


def test_handshake_accepts_expected_rejection(connection):
    connection.getresponse.return_value.status = 403
    verification.check_handshake('/ws/wallet/0', [], 403)
    connection.close.assert_called_once()


@pytest.mark.parametrize('status', (200, 301, 500))
def test_handshake_rejects_http_success_redirect_and_server_failure(connection, status):
    connection.getresponse.return_value.status = status
    with pytest.raises(CommandError, match='expected 101'):
        verification.check_handshake('/ws/trades', [], 101)
    connection.close.assert_called_once()


@pytest.mark.parametrize('bad_header', ('Sec-WebSocket-Accept', 'Sec-WebSocket-Protocol'))
def test_handshake_rejects_invalid_server_negotiation(connection, bad_header):
    original = connection.getresponse.return_value.getheader.side_effect
    connection.getresponse.return_value.getheader.side_effect = (
        lambda name: None if name == bad_header else original(name)
    )
    with pytest.raises(CommandError):
        verification.check_handshake('/ws/trades', ['access_token'], 101)
    connection.close.assert_called_once()


def test_handshake_failure_does_not_echo_credentials(connection):
    connection.getresponse.side_effect = OSError('synthetic-secret')
    with pytest.raises(CommandError, match=r'^WebSocket connection failed \(OSError\)\.$'):
        verification.check_handshake('/ws/trades', ['access_token', 'synthetic-secret'], 101)
    connection.close.assert_called_once()


@pytest.mark.parametrize('enforced', (False, True))
def test_verification_checks_public_private_and_other_user_handshakes(monkeypatch, settings, bucky, enforced):
    settings.ENFORCE_WEBSOCKET_AUTHENTICATION = enforced
    check = Mock()
    monkeypatch.setattr(verification, 'check_handshake', check)
    output = StringIO()

    call_command('verify_websocket_authentication', expect_enforcement='on' if enforced else 'off', stdout=output)

    assert check.call_count == 22
    rejected = 403 if enforced else 101
    token_strings = set()
    for call in check.call_args_list:
        path, protocols, status = call.args
        if path in verification.PUBLIC_PATHS:
            assert status == 101
        elif protocols and protocols[-1] != 'invalid':
            token_strings.add(protocols[-1])
            assert status == (rejected if path.endswith('/0') else 101)
        else:
            assert status == rejected
    assert len(token_strings) == len(verification.PRIVATE_PATHS)
    for token_string in token_strings:
        token = AccessToken(token_string)
        assert token['exp'] - token['iat'] <= 60
        assert token_string not in output.getvalue()
    assert '22 public/private handshakes' in output.getvalue()


def test_verification_refuses_unexpected_rollout_mode(monkeypatch, settings):
    settings.ENFORCE_WEBSOCKET_AUTHENTICATION = False
    check = Mock()
    monkeypatch.setattr(verification, 'check_handshake', check)
    with pytest.raises(CommandError, match='expected mode on'):
        call_command('verify_websocket_authentication', expect_enforcement='on')
    check.assert_not_called()


def test_announcement_commits_record_before_broadcast(monkeypatch, django_capture_on_commit_callbacks):
    previous = FrontendDeployment.objects.create()
    broadcast = Mock()
    monkeypatch.setattr(announcement.FrontendDeploymentConsumer, 'stream_frontend_deployment', broadcast)
    with django_capture_on_commit_callbacks(execute=True):
        call_command('announce_frontend_deployment', expected_previous_id=previous.pk, stdout=StringIO())
        broadcast.assert_not_called()
    latest = FrontendDeployment.get_latest_deployment()
    assert latest.pk != previous.pk
    assert latest.deployed_by is None
    broadcast.assert_called_once()
    assert broadcast.call_args.kwargs['deployment_data']['id'] == latest.pk
    assert broadcast.call_args.kwargs['message_type'].value == 'update.frontend_deployment'


def test_announcement_rejects_stale_retry_without_broadcast(monkeypatch):
    previous = FrontendDeployment.objects.create()
    broadcast = Mock()
    monkeypatch.setattr(announcement.FrontendDeploymentConsumer, 'stream_frontend_deployment', broadcast)
    count = FrontendDeployment.objects.count()
    with pytest.raises(CommandError, match='latest frontend deployment changed'):
        call_command('announce_frontend_deployment', expected_previous_id=previous.pk - 1)
    assert FrontendDeployment.objects.count() == count
    broadcast.assert_not_called()
