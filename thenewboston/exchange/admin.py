from django.contrib import admin

from .models import AssetPair, ExchangeOrder, OrderProcessingLock, Trade, TradeHistoryItem
from .models.exchange_order import CHANGEABLE_FIELDS


class AssetPairListFilter(admin.RelatedFieldListFilter):
    def field_choices(self, field, request, model_admin):
        if field.choices is not None:
            return field.choices

        queryset = field.remote_field.model._default_manager.complex_filter(field.get_limit_choices_to())
        queryset = queryset.select_related('primary_currency', 'secondary_currency')
        if ordering := self.field_admin_ordering(field, request, model_admin):
            queryset = queryset.order_by(*ordering)
        return [(getattr(asset_pair, field.target_field.attname), str(asset_pair)) for asset_pair in queryset]


@admin.register(AssetPair)
class AssetPairAdmin(admin.ModelAdmin):
    list_select_related = ('primary_currency', 'secondary_currency')


@admin.register(ExchangeOrder)
class ExchangeOrderAdmin(admin.ModelAdmin):
    list_select_related = ('owner', 'asset_pair__primary_currency', 'asset_pair__secondary_currency')
    list_display = (
        'id',
        'owner',
        'asset_pair',
        'side',
        'quantity',
        'price',
        'filled_quantity',
        'status',
        'created_date',
        'modified_date',
    )
    list_filter = ('side', 'status', ('asset_pair', AssetPairListFilter))
    # no set arithmetics to keep the field order
    readonly_fields = [
        field_name for field_name in ExchangeOrder.get_field_names() if field_name not in CHANGEABLE_FIELDS
    ]
    search_fields = (
        'owner__username',
        'owner__first_name',
        'owner__last_name',
        'asset_pair__primary_currency__ticker',
        'asset_pair__secondary_currency__ticker',
    )
    ordering = ('-created_date', '-pk')
    date_hierarchy = 'created_date'


@admin.register(OrderProcessingLock)
class OrderProcessingLockAdmin(admin.ModelAdmin):
    list_display = ('id', 'acquired_at', 'trade_at', 'extra')


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_select_related = (
        'buy_order__asset_pair__primary_currency',
        'buy_order__asset_pair__secondary_currency',
        'sell_order__asset_pair__primary_currency',
        'sell_order__asset_pair__secondary_currency',
    )
    list_display = ('id', 'buy_order', 'sell_order', 'filled_quantity', 'price', 'overpayment_amount', 'created_date')
    ordering = ('-created_date', '-pk')


@admin.register(TradeHistoryItem)
class TradeHistoryItemAdmin(admin.ModelAdmin):
    list_select_related = ('asset_pair__primary_currency', 'asset_pair__secondary_currency')
    list_display = (
        'id',
        'asset_pair',
        'price',
        'change_1h',
        'change_24h',
        'change_7d',
        'volume_24h',
        'market_cap',
        'sparkline',
        'modified_date',
    )
    ordering = ('asset_pair__primary_currency__ticker', 'asset_pair__secondary_currency__ticker')
