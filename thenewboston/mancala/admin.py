from django.contrib import admin

from .models import MancalaEvent, MancalaLedgerEntry, MancalaMatch


class ReadOnlyAdmin(admin.ModelAdmin):
    """Game state and money records are inspectable but only services may mutate them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MancalaMatch)
class MancalaMatchAdmin(ReadOnlyAdmin):
    list_display = ['id', 'host', 'guest', 'mode', 'status', 'stake_amount', 'winner', 'result_reason']
    list_filter = ['mode', 'status']


@admin.register(MancalaEvent, MancalaLedgerEntry)
class MancalaAuditAdmin(ReadOnlyAdmin):
    pass
