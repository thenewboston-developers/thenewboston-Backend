from django.contrib import admin
from django.urls import include, path

import thenewboston.authentication.urls
import thenewboston.users.urls

API_PREFIX = 'api/'

urlpatterns = [
    path('admin/', admin.site.urls),
    path(API_PREFIX, include(thenewboston.authentication.urls)),
    path(API_PREFIX, include(thenewboston.users.urls)),
]
