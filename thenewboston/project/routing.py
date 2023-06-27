from django.urls import re_path

from thenewboston.orders.consumers.order import OrderConsumer
from thenewboston.wallets.consumers.wallet import WalletConsumer

websocket_urlpatterns = [
    re_path(r'^ws/orders$', OrderConsumer.as_asgi()),
    re_path(r'^ws/wallet/(?P<user_id>\d+)$', WalletConsumer.as_asgi()),
]
