from datetime import timedelta

from django.contrib.postgres.fields import ArrayField
from django.db import transaction
from django.db.models import CASCADE, F, FloatField, Max, OneToOneField, PositiveBigIntegerField, Q, Sum
from django.utils import timezone

from thenewboston.currencies.models import Mint
from thenewboston.general.managers import CustomManager
from thenewboston.general.models.created_modified import CreatedModified

SPARKLINE_OFFSETS = range(24 * 7 - 6, 0, -6)  # in hours
# The 24-hour price is shared by the sparkline and percentage change.
PRICE_OFFSETS = sorted(set(SPARKLINE_OFFSETS) | {1, 24, 24 * 7})


def calculate_change_percent(current_price, past_price):
    if current_price is None or past_price is None:
        return None

    return ((current_price / past_price) - 1) * 100  # same as ((current_price - past_price) / past_price) * 100


class TradeHistoryItemManager(CustomManager):
    def update_for_currency_pair(self, asset_pair_id):
        self.update_for_currency_pairs([asset_pair_id])

    def update_for_currency_pairs(self, asset_pair_ids):
        # The number of queries does not depend on the number of currency pairs or trades.
        from .trade import Trade

        asset_pair_ids = sorted(set(asset_pair_ids))
        if not asset_pair_ids:
            return

        with transaction.atomic():
            # Updates of the same items wait here, so the trades read below are never older than the trades
            # an update that finished earlier has read.
            list(
                self.select_for_update()
                .filter(asset_pair_id__in=asset_pair_ids)
                .order_by('pk')
                .values_list('pk', flat=True)
            )

            now = timezone.now()  # bind to the same moment for consistency
            # One pass over the trades finds when each currency pair was last traded before every cutoff,
            # without loading the trade history into memory.
            traded_at = {
                f'traded_at_{offset}h': Max('created_date', filter=Q(created_date__lte=now - timedelta(hours=offset)))
                for offset in PRICE_OFFSETS
            }
            asset_pairs = list(
                Trade.objects.filter_by_asset_pair_ids(asset_pair_ids)
                .values(
                    pair_id=F('buy_order__asset_pair_id'),
                    primary_currency_id=F('buy_order__asset_pair__primary_currency_id'),
                )
                .annotate(
                    traded_at=Max('created_date'),
                    volume_24h=Sum('filled_quantity', filter=Q(created_date__gte=now - timedelta(hours=24))),
                    **traded_at,
                )
                .order_by()
            )
            if not asset_pairs:
                # TODO(dmu) LOW: This is questionable behavior: what if we deleted all trades and
                #                want trade history selfheal?
                return  # we do not do anything if there were no trades at all

            moments = {asset_pair[key] for asset_pair in asset_pairs for key in ('traded_at', *traded_at)} - {None}
            prices = {
                (pair_id, created_date): price
                for pair_id, created_date, price in Trade.objects.filter_by_asset_pair_ids(
                    [asset_pair['pair_id'] for asset_pair in asset_pairs]
                )
                .filter(created_date__in=moments)
                # Trades of the same moment are as good as each other, the latest one makes the choice stable
                .order_by('pk')
                .values_list('buy_order__asset_pair_id', 'created_date', 'price')
            }
            minted_amounts = dict(
                Mint.objects.filter(currency_id__in={asset_pair['primary_currency_id'] for asset_pair in asset_pairs})
                .values_list('currency_id')
                .annotate(total=Sum('amount'))
                .order_by()
            )

            items = []
            for asset_pair in asset_pairs:
                pair_id = asset_pair['pair_id']
                current_price = prices[pair_id, asset_pair['traded_at']]
                past_prices = {
                    offset: prices.get((pair_id, asset_pair[f'traded_at_{offset}h'])) for offset in PRICE_OFFSETS
                }
                items.append(
                    self.model(
                        asset_pair_id=pair_id,
                        price=current_price,
                        change_1h=calculate_change_percent(current_price, past_prices[1]) or 0,
                        change_24h=calculate_change_percent(current_price, past_prices[24]) or 0,
                        change_7d=calculate_change_percent(current_price, past_prices[24 * 7]) or 0,
                        volume_24h=asset_pair['volume_24h'] or 0,
                        market_cap=current_price * minted_amounts.get(asset_pair['primary_currency_id'], 0),
                        sparkline=[past_prices[offset] for offset in SPARKLINE_OFFSETS] + [current_price],
                    )
                )

            self.bulk_create(
                items,
                update_conflicts=True,
                unique_fields=['asset_pair'],
                update_fields=[
                    'price',
                    'change_1h',
                    'change_24h',
                    'change_7d',
                    'volume_24h',
                    'market_cap',
                    'sparkline',
                    'modified_date',
                ],
            )


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
