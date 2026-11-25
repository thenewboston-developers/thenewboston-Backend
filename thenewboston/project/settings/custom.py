"""
Settings specific to this application only (no Django or third party settings)
"""

IN_DOCKER = False

# TODO(dmu) MEDIUM: Do we need both `ACCOUNT_NUMBER` and `SIGNING_KEY`.
#                   Can't we derive `ACCOUNT_NUMBER` from `SIGNING_KEY`?
ACCOUNT_NUMBER = None
SIGNING_KEY = None

ENV_NAME = 'unknown'

SENTRY_EVENT_LEVEL = 'WARNING'
SENTRY_DSN = None
SENTRY_TRACES_SAMPLE_RATE = 0.1

POSTHOG_ENABLED = False
POSTHOG_API_KEY = ''
POSTHOG_HOST = ''

LOGGING_MIDDLEWARE_SKIPPED_REQUEST_MEDIA_TYPES = ('multipart/form-data',)
LOGGING_MIDDLEWARE_SKIPPED_RESPONSE_MEDIA_TYPES = ('text/html', 'text/javascript')

ORDER_PROCESSING_REDIS_URL = 'redis://localhost:6379'
ORDER_PROCESSING_CHANNEL_NAME = 'order_processing'
ORDER_PROCESSING_CHANNEL_GET_MESSAGE_TIMEOUT_SECONDS = 10  # None is an option for infinite timeout
ONE_TRADE_PER_ITERATION = False

# The sockets that stream the private events of one user (notifications, wallet, Connect Five) accept only that user
# once this is on. While it is off they accept every connection, as they always did, and log the ones that would be
# rejected, so the backend can be deployed before the frontend that sends the access token.
ENFORCE_WEBSOCKET_AUTHENTICATION = False

# Misc
DEFAULT_CURRENCY_TICKER = 'TNB'
IS_DEPLOYED = False
LOG_DATABASE_QUERIES = False
