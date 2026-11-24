from django.contrib import admin

from .models import BattleshipEvent, BattleshipLedgerEntry, BattleshipMatch


class ReadOnlyAdmin(admin.ModelAdmin):
    """Game state and money records are inspectable but only services may mutate them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Saving a stale form would overwrite a shot or a settlement that committed meanwhile.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BattleshipMatch)
class BattleshipMatchAdmin(ReadOnlyAdmin):
    list_display = ['id', 'host', 'guest', 'mode', 'status', 'phase', 'stake_amount', 'winner']
    list_filter = ['mode', 'status']
    # Administrative inspection must not disclose hidden fleets.
    exclude = ['fleet_host', 'fleet_guest']


@admin.register(BattleshipEvent, BattleshipLedgerEntry)
class BattleshipAuditAdmin(ReadOnlyAdmin):
    pass
