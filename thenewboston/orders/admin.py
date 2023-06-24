from django.contrib import admin

from .models import AssetPair, Order, Trade

admin.site.register(AssetPair)
admin.site.register(Order)
admin.site.register(Trade)
