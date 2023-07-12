from django.contrib import admin

from .models import AssetPair, ExchangeOrder, Trade

admin.site.register(AssetPair)
admin.site.register(ExchangeOrder)
admin.site.register(Trade)
