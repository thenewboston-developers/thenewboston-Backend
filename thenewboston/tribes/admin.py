from django.contrib import admin

from .models import ActionReceipt, Activity, MoneyEntry, Season


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Season)
class SeasonAdmin(ReadOnlyAdmin):
    list_display = ('id', 'status', 'starts_at', 'ends_at', 'total_deposited', 'total_withdrawn', 'system_revenue')
    list_filter = ('status',)


@admin.register(MoneyEntry)
class MoneyEntryAdmin(ReadOnlyAdmin):
    list_display = ('id', 'season', 'wallet', 'amount', 'reason', 'created_at')
    list_filter = ('reason',)


@admin.register(ActionReceipt)
class ActionReceiptAdmin(ReadOnlyAdmin):
    list_display = ('id', 'season', 'actor', 'action', 'request_id', 'created_at')


@admin.register(Activity)
class ActivityAdmin(ReadOnlyAdmin):
    list_display = ('id', 'season', 'tribe_id', 'user', 'text', 'created_at')
