from django.urls import re_path

from thenewboston.exchange.consumers.exchange_order import ExchangeOrderConsumer
from thenewboston.notifications.consumers.notification import NotificationConsumer
from thenewboston.wallets.consumers.wallet import WalletConsumer

websocket_urlpatterns = [
    re_path(r'^ws/exchange-orders$', ExchangeOrderConsumer.as_asgi()),
    re_path(r'^ws/notifications/(?P<user_id>\d+)$', NotificationConsumer.as_asgi()),
    re_path(r'^ws/wallet/(?P<user_id>\d+)$', WalletConsumer.as_asgi()),
]
