from django.contrib import admin

from .models import Block, Wallet, Wire

admin.site.register(Block)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_select_related = ('owner', 'currency')


@admin.register(Wire)
class WireAdmin(admin.ModelAdmin):
    list_select_related = ('owner', 'currency')
