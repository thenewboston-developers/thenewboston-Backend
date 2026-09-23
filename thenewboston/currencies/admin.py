from django.contrib import admin

from .models import Currency, Mint, Whitepaper

admin.site.register(Currency)


@admin.register(Mint)
class MintAdmin(admin.ModelAdmin):
    list_select_related = ('currency', 'owner')


@admin.register(Whitepaper)
class WhitepaperAdmin(admin.ModelAdmin):
    list_select_related = ('currency',)
