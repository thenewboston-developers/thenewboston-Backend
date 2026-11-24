import re
from contextvars import ContextVar
from uuid import UUID

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.utils import timezone

GAMES = {'backgammon', 'battleship', 'checkers', 'connect_five', 'dots_and_boxes', 'hex', 'mancala', 'reversi'}
SOURCES = {'games_hub', 'game_lobby', 'game_match', 'guest_reward', 'game_fund'}
current_request = ContextVar('product_analytics_request', default=None)


def request_context():
    request = current_request.get()
    if request is None:
        return None
    headers = request.headers
    distinct_id = headers.get('X-POSTHOG-DISTINCT-ID', '')
    # Anonymous browser IDs are UUIDs, while identified IDs must never override authenticated users.
    try:
        distinct_id = str(UUID(distinct_id))
    except (ValueError, TypeError, AttributeError):
        distinct_id = ''
    session_id = headers.get('X-POSTHOG-SESSION-ID', '')
    try:
        session_id = str(UUID(session_id))
    except (ValueError, TypeError, AttributeError):
        session_id = ''
    properties = {}
    game = headers.get('X-POSTHOG-GAME')
    source = headers.get('X-POSTHOG-GAME-SOURCE')
    match_id = headers.get('X-POSTHOG-GAME-MATCH-ID', '')
    if game in GAMES:
        properties['attribution_game'] = game
    if source in SOURCES:
        properties['signup_source'] = source
    if game in GAMES and re.fullmatch(r'[1-9][0-9]{0,14}', match_id):
        properties['attribution_match_id'] = int(match_id)
    for header, key in (
        ('X-POSTHOG-REWARD-OFFER-SEEN', 'reward_offer_seen'),
        ('X-POSTHOG-REWARD-SIGNUP-CLICKED', 'reward_signup_clicked'),
    ):
        if headers.get(header) == '1':
            properties[key] = True
    user = getattr(request, 'user', None)
    return {
        'distinct_id': distinct_id,
        'session_id': session_id,
        'opt_out': headers.get('X-POSTHOG-OPT-OUT') == '1' or headers.get('DNT') == '1',
        'internal_traffic': headers.get('X-POSTHOG-INTERNAL-TRAFFIC') == '1',
        'user_id': user.pk if user and user.is_authenticated else None,
        'guest_session_id': getattr(request, '_analytics_guest_session_id', None),
        'attribution': properties,
        'received_at': getattr(request, '_analytics_received_at', None),
    }


class AnalyticsContextMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self.get_response):
            return self.__acall__(request)
        token = current_request.set(request)
        request._analytics_received_at = timezone.now()
        try:
            return self.get_response(request)
        finally:
            try:
                self.finish_request()
            finally:
                current_request.reset(token)

    async def __acall__(self, request):
        token = current_request.set(request)
        request._analytics_received_at = timezone.now()
        try:
            return await self.get_response(request)
        finally:
            try:
                await sync_to_async(self.finish_request, thread_sensitive=True)()
            finally:
                current_request.reset(token)

    @staticmethod
    def finish_request():
        from .events import record_privacy_choice, safely_record

        safely_record(record_privacy_choice)
