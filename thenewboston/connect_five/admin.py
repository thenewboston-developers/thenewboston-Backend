from django.contrib import admin

from .models import (
    ConnectFiveChallenge,
    ConnectFiveChatMessage,
    ConnectFiveEscrow,
    ConnectFiveLedgerEntry,
    ConnectFiveMatch,
    ConnectFiveMatchEvent,
    ConnectFiveMatchPlayer,
    ConnectFiveStats,
)

admin.site.register(ConnectFiveChallenge)
admin.site.register(ConnectFiveChatMessage)
admin.site.register(ConnectFiveEscrow)
admin.site.register(ConnectFiveLedgerEntry)
admin.site.register(ConnectFiveMatch)
admin.site.register(ConnectFiveMatchEvent)
admin.site.register(ConnectFiveMatchPlayer)
admin.site.register(ConnectFiveStats)
