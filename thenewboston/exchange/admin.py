from django.contrib import admin

from .models import AssetPair, ExchangeOrder, OrderProcessingLock, Trade, TradeHistoryItem

admin.site.register(AssetPair)


@admin.register(ExchangeOrder)
class ExchangeOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'owner', 'primary_currency', 'secondary_currency', 'side', 'quantity', 'price', 'filled_quantity',
        'status', 'created_date', 'modified_date'
    )
    list_filter = (
        'side',
        'status',
        'primary_currency',
        'secondary_currency',
    )
    search_fields = (
        'owner__username',
        'owner__first_name',
        'owner__last_name',
        'primary_currency__ticker',
        'secondary_currency__ticker',
    )
    ordering = ('-created_date', '-pk')
    date_hierarchy = 'created_date'
    readonly_fields = ('created_date', 'modified_date')


@admin.register(OrderProcessingLock)
class OrderProcessingLockAdmin(admin.ModelAdmin):
    list_display = ('id', 'acquired_at', 'trade_at', 'extra')


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ('id', 'buy_order', 'sell_order', 'filled_quantity', 'price', 'overpayment_amount', 'created_date')
    ordering = ('-created_date', '-pk')


@admin.register(TradeHistoryItem)
class TradeHistoryItemAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'primary_currency', 'secondary_currency', 'price', 'change_1h', 'change_24h', 'change_7d', 'volume_24h',
        'market_cap', 'sparkline', 'modified_date'
    )
    ordering = ('primary_currency__ticker', 'secondary_currency__ticker')
