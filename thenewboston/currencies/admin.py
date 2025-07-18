from django.contrib import admin

from .models import Currency, Mint, Whitepaper

admin.site.register(Currency)
admin.site.register(Mint)
admin.site.register(Whitepaper)
