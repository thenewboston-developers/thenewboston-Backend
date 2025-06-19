from django.urls import re_path

from thenewboston.exchange.consumers.asset_pair_exchange_order import AssetPairExchangeOrderConsumer
from thenewboston.exchange.consumers.trade import TradeConsumer
from thenewboston.notifications.consumers.notification import NotificationConsumer
from thenewboston.wallets.consumers.wallet import WalletConsumer

websocket_urlpatterns = [
    re_path(
        r'^ws/exchange-orders/(?P<primary_currency>\d+)/(?P<secondary_currency>\d+)$',
        AssetPairExchangeOrderConsumer.as_asgi()
    ),
    re_path(r'^ws/notifications/(?P<user_id>\d+)$', NotificationConsumer.as_asgi()),
    re_path(r'^ws/trades$', TradeConsumer.as_asgi()),
    re_path(r'^ws/wallet/(?P<user_id>\d+)$', WalletConsumer.as_asgi()),
]
