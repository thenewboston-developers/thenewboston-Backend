from datetime import timedelta

from django.contrib.postgres.fields import ArrayField
from django.db.models import CASCADE, FloatField, ForeignKey, PositiveBigIntegerField, Sum, UniqueConstraint
from django.utils import timezone

from thenewboston.currencies.models.currency import get_total_amount_minted
from thenewboston.general.managers import CustomManager
from thenewboston.general.models.created_modified import CreatedModified


def get_past_price(primary_currency_id, secondary_currency_id, recency: timedelta | None = None, now=None):
    from .trade import Trade

    qs = Trade.objects.filter_by_currency_pair(primary_currency_id, secondary_currency_id)
    if recency:
        qs = qs.filter(created_date__lte=(now or timezone.now()) - recency)

    return qs.order_by('-created_date').values_list('price', flat=True).first()


def calculate_change_percent(current_price, past_price):
    if current_price is None or past_price is None:
        return None

    return ((current_price / past_price) - 1) * 100  # same as ((current_price - past_price) / past_price) * 100


class TradeHistoryItemManager(CustomManager):

    def update_for_currency_pair(self, primary_currency_id, secondary_currency_id):
        from .trade import Trade

        if (current_price := get_past_price(primary_currency_id, secondary_currency_id)) is None:
            # TODO(dmu) LOW: This is questionable behavior: what if we deleted all trades and
            #                want trade history selfheal?
            return  # we do not do anything if there were no trades at all

        now = timezone.now()  # bind to the same moment for consistency
        sparkline = [
            get_past_price(primary_currency_id, secondary_currency_id, recency=timedelta(hours=offset), now=now)
            for offset in range(24 * 7 - 6, 0, -6)
        ]
        sparkline.append(current_price)

        defaults = {
            'price':
                current_price,
            'change_1h':
                calculate_change_percent(
                    current_price,
                    get_past_price(primary_currency_id, secondary_currency_id, recency=timedelta(hours=1), now=now)
                ) or 0,
            'change_24h':
                calculate_change_percent(
                    current_price,
                    get_past_price(primary_currency_id, secondary_currency_id, recency=timedelta(hours=24), now=now)
                ) or 0,
            'change_7d':
                calculate_change_percent(
                    current_price,
                    get_past_price(
                        primary_currency_id, secondary_currency_id, recency=timedelta(hours=24 * 7), now=now
                    )
                ) or 0,
            'volume_24h':
                Trade.objects.filter_by_currency_pair(primary_currency_id, secondary_currency_id).filter(
                    created_date__gte=now - timedelta(hours=24)
                ).aggregate(volume=Sum('filled_quantity'))['volume'] or 0,
            'market_cap':
                current_price * get_total_amount_minted(primary_currency_id),
            'sparkline':
                sparkline,
        }
        self.update_or_create(
            primary_currency_id=primary_currency_id,
            secondary_currency_id=secondary_currency_id,
            defaults=defaults,
        )


class TradeHistoryItem(CreatedModified):
    primary_currency = ForeignKey('currencies.Currency', on_delete=CASCADE, related_name='primary_trade_history_items')
    secondary_currency = ForeignKey(
        'currencies.Currency', on_delete=CASCADE, related_name='secondary_trade_history_items'
    )

    price = PositiveBigIntegerField()
    change_1h = FloatField()
    change_24h = FloatField()
    change_7d = FloatField()
    volume_24h = PositiveBigIntegerField()
    market_cap = PositiveBigIntegerField()
    sparkline = ArrayField(base_field=PositiveBigIntegerField(null=True, blank=True), blank=True, default=list)

    objects = TradeHistoryItemManager()

    class Meta:
        constraints = [
            UniqueConstraint(fields=['primary_currency', 'secondary_currency'], name='unique_trade_history_item')
        ]
