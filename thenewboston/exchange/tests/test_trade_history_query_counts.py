from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from thenewboston.exchange.models import AssetPair, ExchangeOrder, Trade, TradeHistoryItem
from thenewboston.exchange.models.exchange_order import ExchangeOrderSide


def create_trades(asset_pair, owner, entries):
    # This fixture only needs persisted history; skip order reservation and trade notifications.
    buy_order, sell_order = ExchangeOrder.objects.bulk_create(
        [
            ExchangeOrder(owner=owner, asset_pair=asset_pair, side=side, quantity=1000, price=1)
            for side in (ExchangeOrderSide.BUY, ExchangeOrderSide.SELL)
        ]
    )
    Trade.objects.bulk_create(
        [
            Trade(
                buy_order=buy_order,
                sell_order=sell_order,
                created_date=created_at,
                price=price,
                filled_quantity=quantity,
                overpayment_amount=0,
            )
            for created_at, price, quantity in entries
        ]
    )


def create_history_item(asset_pair):
    return TradeHistoryItem.objects.create(
        asset_pair=asset_pair,
        price=1,
        change_1h=0,
        change_24h=0,
        change_7d=0,
        volume_24h=0,
        market_cap=0,
        sparkline=[],
    )


@pytest.mark.django_db
@pytest.mark.usefixtures('tnb_mint', 'yyy_mint')
@freeze_time('2026-09-22 12:00:00')
def test_trade_history_batches_prices_and_preserves_cutoff_edges(
    django_assert_num_queries, bucky, tnb_currency, yyy_currency, zzz_currency
):
    now = timezone.now()
    tick = timedelta(microseconds=1)
    pair = AssetPair.objects.create(primary_currency=tnb_currency, secondary_currency=yyy_currency)
    create_trades(
        pair,
        bucky,
        [
            (now - timedelta(hours=169), 10, 1),
            (now - timedelta(hours=168), 20, 2),
            (now - timedelta(hours=168) + tick, 22, 3),
            (now - timedelta(hours=162), 30, 4),
            (now - timedelta(hours=162) + tick, 33, 5),
            (now - timedelta(hours=24) - tick, 40, 6),
            (now - timedelta(hours=24), 50, 7),
            (now - timedelta(hours=24) + tick, 55, 8),
            (now - timedelta(hours=6), 60, 9),
            (now - timedelta(hours=6) + tick, 66, 10),
            (now - timedelta(hours=1) - tick, 70, 11),
            (now - timedelta(hours=1), 80, 12),
            (now - timedelta(hours=1) + tick, 88, 13),
            (now, 100, 14),
        ],
    )
    other_pair = AssetPair.objects.create(primary_currency=yyy_currency, secondary_currency=zzz_currency)
    create_trades(other_pair, bucky, [(now - timedelta(hours=200), 7, 1), (now, 14, 2)])
    item = create_history_item(pair)
    other_item = create_history_item(other_pair)

    # One SELECT gets all historical prices, followed by volume/mint totals and the locked update.
    with django_assert_num_queries(7):
        TradeHistoryItem.objects.update_for_currency_pair(pair.id)
    with django_assert_num_queries(7):
        TradeHistoryItem.objects.update_for_currency_pair(other_pair.id)

    item.refresh_from_db()
    assert item.price == 100
    assert item.change_1h == pytest.approx(25)
    assert item.change_24h == pytest.approx(100)
    assert item.change_7d == pytest.approx(400)
    assert item.sparkline == [30] + [33] * 22 + [50, 55, 55, 60, 100]
    assert item.volume_24h == 84
    assert item.market_cap == 10_000_000
    other_item.refresh_from_db()
    assert other_item.price == 14
    assert other_item.change_1h == pytest.approx(100)
    assert other_item.change_24h == pytest.approx(100)
    assert other_item.change_7d == pytest.approx(100)
    assert other_item.sparkline == [7] * 27 + [14]
    assert other_item.volume_24h == 2
    assert other_item.market_cap == 2_800_000


@pytest.mark.django_db
@pytest.mark.parametrize('trade_count', [1, 40])
@freeze_time('2026-09-22 12:00:00')
def test_trade_history_new_item_has_constant_queries_and_missing_cutoffs(
    django_assert_num_queries, bucky, tnb_currency, yyy_currency, trade_count
):
    now = timezone.now()
    pair = AssetPair.objects.create(primary_currency=tnb_currency, secondary_currency=yyy_currency)
    create_trades(
        pair,
        bucky,
        [(now - timedelta(seconds=index), 42, 3) for index in range(trade_count)],
    )

    with django_assert_num_queries(9):
        TradeHistoryItem.objects.update_for_currency_pair(pair.id)

    item = TradeHistoryItem.objects.get(asset_pair=pair)
    assert item.price == 42
    assert item.change_1h == item.change_24h == item.change_7d == 0
    assert item.sparkline == [None] * 27 + [42]
    assert item.volume_24h == 3 * trade_count
    assert item.market_cap == 0


@pytest.mark.django_db
@pytest.mark.parametrize('has_existing_item', [False, True])
def test_trade_history_without_trades_is_unchanged(
    django_assert_num_queries, tnb_currency, yyy_currency, has_existing_item
):
    pair = AssetPair.objects.create(primary_currency=tnb_currency, secondary_currency=yyy_currency)
    original = create_history_item(pair) if has_existing_item else None

    with django_assert_num_queries(1):
        TradeHistoryItem.objects.update_for_currency_pair(pair.id)

    if original is None:
        assert not TradeHistoryItem.objects.filter(asset_pair=pair).exists()
    else:
        item = TradeHistoryItem.objects.get(asset_pair=pair)
        assert item.pk == original.pk
        assert item.price == original.price
        assert item.sparkline == original.sparkline
        assert item.modified_date == original.modified_date
