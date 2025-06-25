from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

import thenewboston.authentication.urls
import thenewboston.currencies.urls
import thenewboston.exchange.urls
import thenewboston.general.urls
import thenewboston.invitations.urls
import thenewboston.notifications.urls
import thenewboston.social.urls
import thenewboston.users.urls
import thenewboston.wallets.urls
import thenewboston.web.urls

API_PREFIX = 'api/'

urlpatterns = [
    path('admin/', admin.site.urls),
    path(API_PREFIX, include(thenewboston.authentication.urls)),
    path(API_PREFIX, include(thenewboston.currencies.urls)),
    path(API_PREFIX, include(thenewboston.exchange.urls)),
    path(API_PREFIX, include(thenewboston.general.urls)),
    path(API_PREFIX, include(thenewboston.invitations.urls)),
    path(API_PREFIX, include(thenewboston.notifications.urls)),
    path(API_PREFIX, include(thenewboston.social.urls)),
    path(API_PREFIX, include(thenewboston.users.urls)),
    path(API_PREFIX, include(thenewboston.wallets.urls)),
    path('', include(thenewboston.web.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
