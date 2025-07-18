import pytest

from thenewboston.exchange.order_processing.engine import find_matching_orders

from .factories.exchange_order import make_buy_order, make_sell_order


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'bucky_zzz_wallet', 'dmitry_tnb_wallet', 'dmitry_zzz_wallet')
def test_find_matching_orders(bucky, dmitry, tnb_currency, yyy_currency, zzz_currency):
    sell_order_1 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=99)
    sell_order_2 = make_sell_order(dmitry, tnb_currency, yyy_currency, price=100)
    sell_order_other_1 = make_sell_order(dmitry, tnb_currency, zzz_currency, price=59)
    sell_order_other_2 = make_sell_order(dmitry, tnb_currency, zzz_currency, price=50)
    buy_order_other_1 = make_buy_order(bucky, tnb_currency, zzz_currency, price=62)
    buy_order_other_2 = make_buy_order(bucky, tnb_currency, zzz_currency, price=63)
    buy_order_1 = make_buy_order(bucky, tnb_currency, yyy_currency, price=102)
    buy_order_2 = make_buy_order(bucky, tnb_currency, yyy_currency, price=103)

    assert find_matching_orders(0, 0, []) is None  # not possible in production
    assert find_matching_orders(0, 1, [sell_order_1]) is None  # not possible in production
    assert find_matching_orders(0, 1, [buy_order_1]) is None  # not possible in production
    assert find_matching_orders(0, 1, [sell_order_1, buy_order_1]) == [0, 1]
    assert find_matching_orders(0, 2, [sell_order_1, sell_order_2, buy_order_1]) == [0, 2]
    assert find_matching_orders(1, 2, [sell_order_1, sell_order_2, buy_order_1]) == [1, 2]  # run out buy
    assert find_matching_orders(0, 1, [sell_order_1, buy_order_1, buy_order_1]) == [0, 1]  # run out sell

    # Advancing to another pair
    potentially_matching_orders = [
        sell_order_1,  # 0
        sell_order_2,  # 1
        sell_order_other_1,  # 2
        sell_order_other_2,  # 3
        buy_order_other_2,  # tail_index - 3 (5)
        buy_order_other_1,  # tail_index - 2 (6)
        buy_order_2,  # tail_index - 1 (7)
        buy_order_1,  # tail_index (8)
    ]
    tail_index = len(potentially_matching_orders) - 1
    assert find_matching_orders(0, tail_index, potentially_matching_orders) == [0, tail_index]
    assert find_matching_orders(1, tail_index, potentially_matching_orders) == [1, tail_index]
    assert find_matching_orders(2, tail_index, potentially_matching_orders) == [2, tail_index - 2]
    assert find_matching_orders(3, tail_index, potentially_matching_orders) == [3, tail_index - 2]
    assert find_matching_orders(3, tail_index - 1, potentially_matching_orders) == [3, tail_index - 2]
    assert find_matching_orders(2, tail_index - 1, potentially_matching_orders) == [2, tail_index - 2]
    assert find_matching_orders(2, tail_index - 2, potentially_matching_orders) == [2, tail_index - 2]
    assert find_matching_orders(3, tail_index - 1, potentially_matching_orders) == [3, tail_index - 2]
    assert find_matching_orders(3, tail_index - 3, potentially_matching_orders) == [3, tail_index - 3]

    # AI generated tests:
    # Mismatched currency pairs - should return None
    assert find_matching_orders(0, 1, [sell_order_other_1, buy_order_1]) is None

    # Sell price higher than buy price - no match
    assert find_matching_orders(
        0, 1, [make_sell_order(dmitry, tnb_currency, yyy_currency, price=110), buy_order_1]
    ) is None

    # Valid sell comes after valid buy - indices reversed
    assert find_matching_orders(1, 0, [buy_order_1, sell_order_1]) is None

    # Repeated valid matches, first one should be returned
    assert find_matching_orders(0, 4,
                                [sell_order_1, sell_order_2, buy_order_other_1, buy_order_1, buy_order_2]) == [0, 4]

    # Identical sell and buy pairs and price match
    assert find_matching_orders(0, 1, [sell_order_2,
                                       make_buy_order(bucky, tnb_currency, yyy_currency, price=100)]) == [0, 1]
