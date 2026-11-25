import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thenewboston.project.settings')
asgi_application = get_asgi_application()  # this does `django.setup()` there must be here

# The following line must go after `django.setup()`
from django.conf import settings  # noqa: E402, I202 # isort: skip
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware  # noqa: E402 # isort: skip
from thenewboston.authentication.websocket import AccessTokenAuthMiddleware  # noqa: E402 # isort: skip
from thenewboston.project.routing import websocket_urlpatterns  # noqa: E402 # isort: skip

websocket_application = URLRouter(websocket_urlpatterns)
if settings.SENTRY_DSN:
    websocket_application = SentryAsgiMiddleware(websocket_application)

# Outermost on purpose: it takes the access token out of the scope before Sentry or anything else can record it
websocket_application = AccessTokenAuthMiddleware(websocket_application)

application = ProtocolTypeRouter(
    {
        'http': asgi_application,
        'websocket': websocket_application,
    }
)
