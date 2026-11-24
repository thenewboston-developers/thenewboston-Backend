from django.contrib import admin

from .models import CheckersEvent, CheckersLedgerEntry, CheckersMatch


@admin.register(CheckersMatch)
class CheckersMatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'white', 'black', 'mode', 'status', 'stake_amount', 'winner']
    list_filter = ['mode', 'status']

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CheckersEvent, CheckersLedgerEntry)
class CheckersAuditAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
