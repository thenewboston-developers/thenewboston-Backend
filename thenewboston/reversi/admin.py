from django.contrib import admin

from .models import ReversiEvent, ReversiLedgerEntry, ReversiMatch


class ReadOnlyAdmin(admin.ModelAdmin):
    """Inspection only: editing a match here would bypass settlement."""

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Saving a stale form would overwrite a move or a settlement that committed meanwhile.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReversiMatch)
class ReversiMatchAdmin(ReadOnlyAdmin):
    list_display = ['id', 'host', 'guest', 'mode', 'status', 'stake_amount', 'winner', 'result_reason']
    list_filter = ['mode', 'status']
    list_select_related = ['host', 'guest']


@admin.register(ReversiEvent, ReversiLedgerEntry)
class ReversiAuditAdmin(ReadOnlyAdmin):
    pass
