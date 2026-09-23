from datetime import timedelta

from django.contrib.postgres.fields import ArrayField
from django.db.models import CASCADE, FloatField, OneToOneField, OuterRef, PositiveBigIntegerField, Subquery, Sum
from django.utils import timezone

from thenewboston.currencies.models.currency import get_total_amount_minted
from thenewboston.exchange.models import AssetPair
from thenewboston.general.managers import CustomManager
from thenewboston.general.models.created_modified import CreatedModified


def calculate_change_percent(current_price, past_price):
    if current_price is None or past_price is None:
        return None

    return ((current_price / past_price) - 1) * 100  # same as ((current_price - past_price) / past_price) * 100


class TradeHistoryItemManager(CustomManager):
    def update_for_currency_pair(self, asset_pair_id):
        from .trade import Trade

        now = timezone.now()  # bind to the same moment for consistency
        sparkline_offsets = range(24 * 7 - 6, 0, -6)
        prices = Trade.objects.filter_by_asset_pair(OuterRef('pk')).order_by('-created_date').values('price')
        # Fetch every cutoff in one statement without loading the full trade history into memory.
        # The 24-hour price is shared by the sparkline and percentage change.
        historical_prices = {
            f'price_{offset}h': Subquery(prices.filter(created_date__lte=now - timedelta(hours=offset))[:1])
            for offset in sorted(set(sparkline_offsets) | {1, 24, 24 * 7})
        }
        asset_pair = (
            AssetPair.objects.filter(pk=asset_pair_id)
            .annotate(current_price=Subquery(prices[:1]), **historical_prices)
            .values('primary_currency_id', 'current_price', *historical_prices)
            .first()
        )
        if asset_pair is None or (current_price := asset_pair['current_price']) is None:
            # TODO(dmu) LOW: This is questionable behavior: what if we deleted all trades and
            #                want trade history selfheal?
            return  # we do not do anything if there were no trades at all

        sparkline = [asset_pair[f'price_{offset}h'] for offset in sparkline_offsets]
        sparkline.append(current_price)

        defaults = {
            'price': current_price,
            'change_1h': calculate_change_percent(current_price, asset_pair['price_1h']) or 0,
            'change_24h': calculate_change_percent(current_price, asset_pair['price_24h']) or 0,
            'change_7d': calculate_change_percent(current_price, asset_pair['price_168h']) or 0,
            'volume_24h': Trade.objects.filter_by_asset_pair(asset_pair_id)
            .filter(created_date__gte=now - timedelta(hours=24))
            .aggregate(volume=Sum('filled_quantity'))['volume']
            or 0,
            'market_cap': current_price * get_total_amount_minted(asset_pair['primary_currency_id']),
            'sparkline': sparkline,
        }
        self.update_or_create(asset_pair_id=asset_pair_id, defaults=defaults)


class TradeHistoryItem(CreatedModified):
    asset_pair = OneToOneField('AssetPair', on_delete=CASCADE, related_name='trade_history_items', null=True)

    price = PositiveBigIntegerField()
    change_1h = FloatField()
    change_24h = FloatField()
    change_7d = FloatField()
    volume_24h = PositiveBigIntegerField()
    market_cap = PositiveBigIntegerField()
    sparkline = ArrayField(base_field=PositiveBigIntegerField(null=True, blank=True), blank=True, default=list)

    objects = TradeHistoryItemManager()
