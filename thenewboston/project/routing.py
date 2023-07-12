from django.urls import re_path

from thenewboston.exchange.consumers.exchange_order import ExchangeOrderConsumer
from thenewboston.wallets.consumers.wallet import WalletConsumer

websocket_urlpatterns = [
    re_path(r'^ws/exchange_orders$', ExchangeOrderConsumer.as_asgi()),
    re_path(r'^ws/wallet/(?P<user_id>\d+)$', WalletConsumer.as_asgi()),
]
