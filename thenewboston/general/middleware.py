import logging
from time import time

from django.conf import settings

logger = logging.getLogger(__name__)


def get_request_description(request):
    request_method = request.method
    description = request_method + ' ' + request.build_absolute_uri()
    if request_method in ('POST', 'PUT', 'PATCH'):
        if request.content_type in settings.LOGGING_MIDDLEWARE_SKIPPED_REQUEST_MEDIA_TYPES:
            description += ' (hidden body)'
        else:
            request_body = request.body
            if request_body:
                description += ' BODY: ' + request_body.decode('utf-8', errors='ignore')
            else:
                description += ' (empty body)'

    return description


class LoggingMiddleware:
    """
    Middleware to simplify debugging. Add these lines to local/settings.dev.py / local/settings.unittests.py if
    you wish your request and response to be logged including body:

    MIDDLEWARE += ('thenewboston.general.middleware.LoggingMiddleware',)
    LOGGING['root']['level'] = 'DEBUG'
    LOGGING['loggers']['thenewboston']['level'] = 'DEBUG'
    LOGGING['handlers']['console']['level'] = 'DEBUG'
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.start_time = None

    def __call__(self, request):
        # pylint: disable=protected-access
        logger.debug(get_request_description(request))
        self.start_time = time()

        response = self.get_response(request)

        if self.start_time is not None:
            duration = time() - self.start_time
            self.start_time = None
        else:
            duration = None

        content_type = response.headers.get('content-type')
        if content_type:
            media_type = content_type.split(';')[0]
            if media_type in settings.LOGGING_MIDDLEWARE_SKIPPED_RESPONSE_MEDIA_TYPES:
                return response

        result = []

        def log_streaming_content(content):
            for chunk in content:
                result.append(chunk)
                yield chunk

        if response.streaming:
            response.streaming_content = log_streaming_content(response.streaming_content)
        else:
            result.append(response.content)

        request_description = get_request_description(request)
        body = b''.join(result).decode('utf-8')
        duration = ('duration unknown' if duration is None else f'{duration:.3f}s')

        logger.debug('%s RESPONSE: HTTP%s %s (%s)', request_description, response.status_code, body, duration)

        return response
