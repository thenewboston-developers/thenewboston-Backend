from django.urls import re_path

from thenewboston.connect_five.consumers import ConnectFiveChatConsumer, ConnectFiveConsumer, ConnectFivePublicConsumer
from thenewboston.exchange.consumers import ExchangeOrderConsumer, TradeConsumer
from thenewboston.general.consumers.frontend_deployment import FrontendDeploymentConsumer
from thenewboston.notifications.consumers import NotificationConsumer
from thenewboston.social.consumers import CommentConsumer
from thenewboston.wallets.consumers import WalletConsumer

websocket_urlpatterns = [
    re_path(r'^ws/comments/(?P<post_id>\d+)$', CommentConsumer.as_asgi()),
    re_path(r'^ws/connect-five/chat/(?P<match_id>\d+)$', ConnectFiveChatConsumer.as_asgi()),
    re_path(r'^ws/connect-five/public$', ConnectFivePublicConsumer.as_asgi()),
    re_path(r'^ws/connect-five/(?P<user_id>\d+)$', ConnectFiveConsumer.as_asgi()),
    re_path(r'^ws/exchange-orders$', ExchangeOrderConsumer.as_asgi()),
    re_path(r'^ws/frontend-deployments$', FrontendDeploymentConsumer.as_asgi()),
    re_path(r'^ws/notifications/(?P<user_id>\d+)$', NotificationConsumer.as_asgi()),
    re_path(r'^ws/trades$', TradeConsumer.as_asgi()),
    re_path(r'^ws/wallet/(?P<user_id>\d+)$', WalletConsumer.as_asgi()),
]
