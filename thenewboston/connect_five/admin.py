from django.contrib import admin

from .models import (
    ConnectFiveChallenge,
    ConnectFiveEscrow,
    ConnectFiveLedgerEntry,
    ConnectFiveMatch,
    ConnectFiveMatchEvent,
    ConnectFiveMatchPlayer,
)

admin.site.register(ConnectFiveChallenge)
admin.site.register(ConnectFiveEscrow)
admin.site.register(ConnectFiveLedgerEntry)
admin.site.register(ConnectFiveMatch)
admin.site.register(ConnectFiveMatchEvent)
admin.site.register(ConnectFiveMatchPlayer)
