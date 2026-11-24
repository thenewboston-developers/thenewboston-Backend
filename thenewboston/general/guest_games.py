"""Expiring capability tokens scoped exclusively to free computer matches."""

from django.core import signing
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import GuestGameSession

GUEST_PLAYER = {'id': 0, 'username': 'Guest', 'avatar': None}
TOKEN_SALT = 'thenewboston.guest-games'


def guest_session(request):
    if request is None or request.user.is_authenticated:
        return None
    if hasattr(request, '_guest_game_session'):
        return request._guest_game_session
    token = request.headers.get('X-Guest-Token')
    session = None
    if token:
        try:
            session_id = signing.loads(token, salt=TOKEN_SALT, max_age=7 * 24 * 60 * 60)
            session = GuestGameSession.objects.get(pk=session_id, expires_at__gt=timezone.now())
        except (signing.BadSignature, GuestGameSession.DoesNotExist, ValueError, TypeError) as error:
            raise AuthenticationFailed('Your guest session expired. Start a new guest game.') from error
    request._guest_game_session = session
    # Pass only the verified owner ID into request-scoped analytics, never the capability token.
    if hasattr(request, '_request'):
        request._request._analytics_guest_session_id = session.pk if session else None
    return session


def owns_guest_match(match, session):
    return bool(session and match.guest_session_id == session.pk)


def match_owner(user, session, field):
    if session:
        return {'guest_session': session}
    if user is None or not user.is_authenticated:
        raise PermissionDenied('Start a guest session or sign in to play.')
    return {field: user, 'guest_session__isnull': True}


def lock_match_owner(user, session):
    if session:
        try:
            GuestGameSession.objects.select_for_update().get(pk=session.pk, expires_at__gt=timezone.now())
        except GuestGameSession.DoesNotExist as error:
            raise AuthenticationFailed('Your guest session expired. Start a new guest game.') from error
    else:
        type(user).objects.select_for_update(no_key=True).get(pk=user.pk)


class GuestGameResponseMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.headers.get('X-Guest-Token'):
            response['Cache-Control'] = 'private, no-store'
        return response


class GameAccess(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return True
        session = guest_session(request)
        if request.method in {'GET', 'HEAD', 'OPTIONS'}:
            return bool(session) or getattr(view, 'public_read', True)
        return bool(session) and view.action in getattr(view, 'guest_actions', ())


class GuestSessionThrottle(AnonRateThrottle):
    rate = '20/hour'


class GuestGameSessionView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [GuestSessionThrottle]

    def post(self, request):
        session = GuestGameSession.objects.create()
        response = Response(
            {
                'token': signing.dumps(str(session.pk), salt=TOKEN_SALT),
                'expires_at': session.expires_at,
                'session_id': session.pk,
            },
            status=201,
        )
        response['Cache-Control'] = 'no-store'
        return response
