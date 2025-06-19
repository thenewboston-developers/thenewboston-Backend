from django.urls import re_path

from thenewboston.exchange.consumers import AssetPairExchangeOrderConsumer, TradeConsumer
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.wallets.consumers import WalletConsumer

websocket_urlpatterns = [
    re_path(
        r'^ws/exchange-orders/(?P<primary_currency>\d+)/(?P<secondary_currency>\d+)$',
        AssetPairExchangeOrderConsumer.as_asgi()
    ),
    re_path(r'^ws/notifications/(?P<user_id>\d+)$', NotificationConsumer.as_asgi()),
    re_path(r'^ws/trades$', TradeConsumer.as_asgi()),
    re_path(r'^ws/wallet/(?P<user_id>\d+)$', WalletConsumer.as_asgi()),
]
