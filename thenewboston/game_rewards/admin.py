from django.contrib import admin

from .models import GameFund, GameFundDeposit, GameRewardDecision


class ReadOnlyLedgerAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GameFund)
class GameFundAdmin(ReadOnlyLedgerAdmin):
    list_display = ('id', 'balance', 'total_deposited', 'total_paid', 'enabled')
    readonly_fields = ('id', 'currency', 'balance', 'total_deposited', 'total_paid', 'created_date', 'modified_date')

    def has_change_permission(self, request, obj=None):
        return admin.ModelAdmin.has_change_permission(self, request, obj)

    def save_model(self, request, obj, form, change):
        # Admin forms may have loaded before a payout; never write stale balances.
        obj.save(update_fields=['enabled', 'modified_date'])


@admin.register(GameFundDeposit)
class GameFundDepositAdmin(ReadOnlyLedgerAdmin):
    list_display = ('id', 'donor', 'amount', 'request_id', 'created_date')
    list_select_related = ('donor',)


@admin.register(GameRewardDecision)
class GameRewardDecisionAdmin(ReadOnlyLedgerAdmin):
    list_display = ('id', 'game', 'match_id', 'user', 'status', 'amount', 'created_date')
    list_filter = ('game', 'status')
    list_select_related = ('user',)
