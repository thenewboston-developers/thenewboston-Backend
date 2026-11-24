from django.contrib import admin

from .models import CheckersEvent, CheckersLedgerEntry, CheckersMatch


class ReadOnlyAdmin(admin.ModelAdmin):
    """Game state and money records are inspectable but only services may mutate them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Saving a stale form would overwrite a move or a settlement that committed meanwhile.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CheckersMatch)
class CheckersMatchAdmin(ReadOnlyAdmin):
    list_display = ['id', 'white', 'black', 'mode', 'status', 'stake_amount', 'winner']
    list_filter = ['mode', 'status']


@admin.register(CheckersEvent, CheckersLedgerEntry)
class CheckersAuditAdmin(ReadOnlyAdmin):
    pass
