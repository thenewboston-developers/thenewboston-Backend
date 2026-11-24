from urllib.parse import urlparse

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

import thenewboston.authentication.urls
import thenewboston.backgammon.urls
import thenewboston.battleship.urls
import thenewboston.checkers.urls
import thenewboston.connect_five.urls
import thenewboston.currencies.urls
import thenewboston.exchange.urls
import thenewboston.game_rewards.urls
import thenewboston.general.urls
import thenewboston.invitations.urls
import thenewboston.mancala.urls
import thenewboston.notifications.urls
import thenewboston.reversi.urls
import thenewboston.social.urls
import thenewboston.users.urls
import thenewboston.wallets.urls
import thenewboston.web.urls

API_PREFIX = 'api/'

urlpatterns = [
    path('admin/', admin.site.urls),
    path(API_PREFIX, include(thenewboston.authentication.urls)),
    path(API_PREFIX, include(thenewboston.backgammon.urls)),
    path(API_PREFIX, include(thenewboston.battleship.urls)),
    path(API_PREFIX, include(thenewboston.checkers.urls)),
    path(API_PREFIX, include(thenewboston.connect_five.urls)),
    path(API_PREFIX, include(thenewboston.currencies.urls)),
    path(API_PREFIX, include(thenewboston.exchange.urls)),
    path(API_PREFIX, include(thenewboston.game_rewards.urls)),
    path(API_PREFIX, include(thenewboston.general.urls)),
    path(API_PREFIX, include(thenewboston.invitations.urls)),
    path(API_PREFIX, include(thenewboston.mancala.urls)),
    path(API_PREFIX, include(thenewboston.notifications.urls)),
    path(API_PREFIX, include(thenewboston.reversi.urls)),
    path(API_PREFIX, include(thenewboston.social.urls)),
    path(API_PREFIX, include(thenewboston.users.urls)),
    path(API_PREFIX, include(thenewboston.wallets.urls)),
    path('', include(thenewboston.web.urls)),
]

if settings.DEBUG:
    urlpatterns += static(urlparse(settings.MEDIA_URL).path, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
