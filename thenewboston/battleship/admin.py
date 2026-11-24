from django.contrib import admin

from .models import BattleshipEvent, BattleshipLedgerEntry, BattleshipMatch


@admin.register(BattleshipMatch)
class BattleshipMatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'host', 'guest', 'mode', 'status', 'phase', 'stake_amount', 'winner']
    list_filter = ['mode', 'status']
    # Administrative inspection must not disclose hidden fleets or bypass settlement.
    exclude = ['fleet_host', 'fleet_guest']

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields if field.name not in self.exclude]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BattleshipEvent, BattleshipLedgerEntry)
class BattleshipAuditAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
