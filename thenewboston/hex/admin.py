from django.contrib import admin

from .models import HexEvent, HexLedgerEntry, HexMatch


class ReadOnlyAdmin(admin.ModelAdmin):
    """Game state and money records are inspectable but only services may mutate them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Saving a stale form would overwrite a move or a settlement that committed meanwhile.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HexMatch)
class HexMatchAdmin(ReadOnlyAdmin):
    list_display = ['id', 'red', 'blue', 'mode', 'board_size', 'status', 'stake_amount', 'winner']
    list_filter = ['mode', 'status', 'board_size']


@admin.register(HexEvent, HexLedgerEntry)
class HexAuditAdmin(ReadOnlyAdmin):
    pass
