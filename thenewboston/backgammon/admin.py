from django.contrib import admin

from .models import BackgammonEvent, BackgammonLedgerEntry, BackgammonMatch


@admin.register(BackgammonMatch, BackgammonLedgerEntry, BackgammonEvent)
class BackgammonAuditAdmin(admin.ModelAdmin):
    """Game state and money records are inspectable but only services may mutate them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
