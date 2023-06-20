from django.contrib import admin

from .models import DepositAccount, Wallet

admin.site.register(DepositAccount)
admin.site.register(Wallet)
