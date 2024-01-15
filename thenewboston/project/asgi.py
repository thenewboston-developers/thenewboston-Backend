import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thenewboston.project.settings')
asgi_application = get_asgi_application()  # this does `django.setup()` there must be here

# The following line must go after `django.setup()`
from thenewboston.project.routing import websocket_urlpatterns  # noqa: E402 # isort: skip

application = ProtocolTypeRouter({
    'http': asgi_application,
    'websocket': URLRouter(websocket_urlpatterns),
})
