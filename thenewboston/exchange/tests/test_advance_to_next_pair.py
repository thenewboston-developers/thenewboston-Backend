import pytest

from thenewboston.exchange.order_processing.engine import advance_to_next_pair

from .factories.exchange_order import make_buy_order, make_sell_order


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_tnb_wallet')
def test_next_pair_forward_for_sell(bucky, tnb_currency, yyy_currency, zzz_currency):
    orders = [
        make_sell_order(bucky, tnb_currency, yyy_currency),  # idx 0 – original
        make_sell_order(bucky, tnb_currency, yyy_currency),  # idx 1 – same pair
        make_sell_order(bucky, tnb_currency, zzz_currency),  # idx 2 – different pair ⇒ expected
    ]
    assert advance_to_next_pair(0, orders) == 2


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_yyy_wallet', 'bucky_zzz_wallet')
def test_next_pair_backward_for_buy(bucky, tnb_currency, yyy_currency, zzz_currency):
    orders = [
        make_buy_order(bucky, tnb_currency, yyy_currency),  # idx 0 – different pair ⇒ expected
        make_buy_order(bucky, yyy_currency, zzz_currency),  # idx 1 – same pair as original
        make_buy_order(bucky, yyy_currency, zzz_currency),  # idx 2 – original
    ]
    assert advance_to_next_pair(2, orders) == 0


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_tnb_wallet', 'bucky_yyy_wallet')
def test_exhausted_when_side_switch_encountered(bucky, tnb_currency, yyy_currency):
    orders = [
        make_sell_order(bucky, tnb_currency, yyy_currency),  # idx 0 – original (SELL)
        make_buy_order(bucky, tnb_currency, yyy_currency),  # idx 1 – opposite side ⇒ stop
        make_buy_order(bucky, tnb_currency, yyy_currency),  # idx 2 – never reached
    ]
    assert advance_to_next_pair(0, orders) is None


@pytest.mark.django_db
@pytest.mark.usefixtures('bucky_tnb_wallet')
def test_returns_none_when_no_other_pairs_on_same_side(bucky, tnb_currency, yyy_currency):
    orders = [
        make_sell_order(bucky, tnb_currency, yyy_currency),
        make_sell_order(bucky, tnb_currency, yyy_currency),
        make_sell_order(bucky, tnb_currency, yyy_currency),
    ]

    assert advance_to_next_pair(0, orders) is None
