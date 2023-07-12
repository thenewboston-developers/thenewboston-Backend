from django.contrib import admin

from .models import Block, Wallet, Wire

admin.site.register(Block)
admin.site.register(Wallet)
admin.site.register(Wire)
