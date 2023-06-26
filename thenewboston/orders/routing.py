from django.urls import re_path

from .consumers import OrderJsonWebsocketConsumer

websocket_urlpatterns = [
    re_path(r'^ws/orders$', OrderJsonWebsocketConsumer.as_asgi()),
]
