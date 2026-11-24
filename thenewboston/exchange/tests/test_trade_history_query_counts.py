from datetime import timedelta
from itertools import permutations

import pytest
from django.utils import timezone
from freezegun import freeze_time
from model_bakery import baker

from thenewboston.exchange.business_logic.trade_history import update_trade_history
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

    # A savepoint pair around: the item lock, the trade moments with the volume, their prices, the mint totals
    # and the write.
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

    with django_assert_num_queries(7):
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

    with django_assert_num_queries(4):
        TradeHistoryItem.objects.update_for_currency_pair(pair.id)

    if original is None:
        assert not TradeHistoryItem.objects.filter(asset_pair=pair).exists()
    else:
        item = TradeHistoryItem.objects.get(asset_pair=pair)
        assert item.pk == original.pk
        assert item.price == original.price
        assert item.sparkline == original.sparkline
        assert item.modified_date == original.modified_date


@pytest.mark.django_db
@pytest.mark.usefixtures('tnb_mint')
@pytest.mark.parametrize('pair_count', [1, 6])
@freeze_time('2026-09-22 12:00:00')
def test_update_trade_history_has_constant_queries_for_any_number_of_pairs(
    django_assert_num_queries, bucky, tnb_currency, yyy_currency, zzz_currency, pair_count
):
    now = timezone.now()
    pairs = [
        AssetPair.objects.create(primary_currency=primary_currency, secondary_currency=secondary_currency)
        for primary_currency, secondary_currency in list(permutations([tnb_currency, yyy_currency, zzz_currency], 2))[
            :pair_count
        ]
    ]
    for index, pair in enumerate(pairs, start=1):
        create_trades(pair, bucky, [(now - timedelta(hours=30), index, 1), (now - timedelta(hours=2), index * 3, 5)])
    # A pair whose item exists already is updated in place, the others get a new item
    original = create_history_item(pairs[0])

    # Two queries find the pairs to update, the rest is the same as for a single pair.
    with django_assert_num_queries(9):
        update_trade_history()

    items = {item.asset_pair_id: item for item in TradeHistoryItem.objects.all()}
    assert set(items) == {pair.id for pair in pairs}
    assert items[pairs[0].id].pk == original.pk
    for index, pair in enumerate(pairs, start=1):
        item = items[pair.id]
        assert item.price == index * 3
        assert item.change_1h == 0
        assert item.change_24h == pytest.approx(200)
        assert item.change_7d == 0
        assert item.sparkline == [None] * 22 + [index] * 5 + [index * 3]
        assert item.volume_24h == 5
        assert item.market_cap == (index * 3 * 100_000 if pair.primary_currency_id == tnb_currency.id else 0)


@pytest.mark.django_db
@freeze_time('2026-09-22 12:00:00')
def test_update_trade_history_updates_other_pairs_when_one_pair_fails(bucky, tnb_currency, yyy_currency, zzz_currency):
    now = timezone.now()
    broken_pair = AssetPair.objects.create(primary_currency=tnb_currency, secondary_currency=yyy_currency)
    pair = AssetPair.objects.create(primary_currency=yyy_currency, secondary_currency=zzz_currency)
    create_trades(broken_pair, bucky, [(now, 2, 1)])
    create_trades(pair, bucky, [(now, 7, 3)])
    # The market cap of this currency does not fit into the column
    baker.make('currencies.Mint', currency=tnb_currency, owner=bucky, amount=2**62)
    baker.make('currencies.Mint', currency=yyy_currency, owner=bucky, amount=10)

    update_trade_history()

    item = TradeHistoryItem.objects.get()
    assert item.asset_pair_id == pair.id
    assert item.price == 7
    assert item.volume_24h == 3
    assert item.market_cap == 70
