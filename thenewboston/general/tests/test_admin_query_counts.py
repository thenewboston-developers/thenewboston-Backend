from uuid import uuid4

import pytest
from django.apps import apps
from django.contrib import admin
from django.contrib.admin.templatetags.admin_list import result_list
from django.test import RequestFactory
from django.utils import timezone
from model_bakery import baker

from thenewboston.exchange.admin import AssetPairListFilter
from thenewboston.exchange.models import AssetPair, ExchangeOrder, Trade
from thenewboston.exchange.models.exchange_order import ExchangeOrderSide


def _make_asset_pair(index, owner):
    return baker.make(
        'exchange.AssetPair',
        primary_currency=baker.make('currencies.Currency', owner=owner, ticker=f'P{index:04}'),
        secondary_currency=baker.make('currencies.Currency', owner=owner, ticker=f'S{index:04}'),
    )


def _make_order(asset_pair, owner, side):
    order = ExchangeOrder(asset_pair=asset_pair, owner=owner, side=side, quantity=20, price=10)
    # Changelist fixtures do not need balance reservations, notifications, or matching-engine events.
    ExchangeOrder.objects.bulk_create([order])
    return order


def _make_admin_row(model_label, index):
    owner = baker.make('users.User', username=f'owner_{index}')

    if model_label in ('currencies.Mint', 'currencies.Whitepaper', 'wallets.Wallet', 'wallets.Wire'):
        currency = baker.make('currencies.Currency', owner=owner, ticker=f'C{index:04}')
        kwargs = {'owner': owner, 'currency': currency}
        if model_label == 'currencies.Mint':
            obj = baker.make(model_label, amount=10, **kwargs)
        elif model_label == 'currencies.Whitepaper':
            obj = baker.make(model_label, content=f'Whitepaper {index}', **kwargs)
        elif model_label == 'wallets.Wallet':
            obj = baker.make(model_label, balance=10, **kwargs)
        else:
            obj = baker.make(model_label, id=uuid4(), amount=10, transaction_fee=1, **kwargs)
        return obj, [str(obj)]

    if model_label == 'invitations.Invitation':
        recipient = baker.make('users.User', username=f'recipient_{index}') if index % 2 == 0 else None
        obj = baker.make(model_label, owner=owner, recipient=recipient, code=f'I{index:05}')
        return obj, [str(obj)]

    if model_label == 'invitations.InvitationLimit':
        obj = baker.make(model_label, owner=owner, amount=10)
        return obj, [str(obj)]

    if model_label == 'social.Follower':
        obj = baker.make(model_label, follower=owner, following=baker.make('users.User', username=f'following_{index}'))
        return obj, [str(obj)]

    if model_label == 'social.PostLike':
        post_owner = baker.make('users.User', username=f'post_owner_{index}')
        post = baker.make('social.Post', owner=post_owner, content=f'Post {index}')
        obj = baker.make(model_label, user=owner, post=post)
        return obj, [str(obj)]

    if model_label == 'users.UserAgreement':
        obj = baker.make(
            model_label, user=owner, terms_agreed_at=timezone.now(), privacy_policy_agreed_at=timezone.now()
        )
        return obj, [str(obj)]

    asset_pair = _make_asset_pair(index, owner)
    if model_label == 'exchange.AssetPair':
        return asset_pair, [str(asset_pair)]

    if model_label == 'exchange.ExchangeOrder':
        order = _make_order(asset_pair, owner, ExchangeOrderSide.BUY)
        return order, [owner.username, str(asset_pair)]

    if model_label == 'exchange.Trade':
        buy_order = _make_order(asset_pair, owner, ExchangeOrderSide.BUY)
        seller = baker.make('users.User', username=f'seller_{index}')
        sell_order = _make_order(asset_pair, seller, ExchangeOrderSide.SELL)
        trade = Trade(buy_order=buy_order, sell_order=sell_order, filled_quantity=5, price=10, overpayment_amount=0)
        Trade.objects.bulk_create([trade])
        return trade, [str(buy_order), str(sell_order)]

    assert model_label == 'exchange.TradeHistoryItem'
    item = baker.make(model_label, asset_pair=asset_pair, sparkline=[10, 11])
    return item, [str(asset_pair)]


@pytest.mark.django_db
@pytest.mark.parametrize('row_count', [1, 4])
@pytest.mark.parametrize(
    'model_label',
    [
        'currencies.Mint',
        'currencies.Whitepaper',
        'wallets.Wallet',
        'wallets.Wire',
        'invitations.Invitation',
        'invitations.InvitationLimit',
        'social.Follower',
        'social.PostLike',
        'users.UserAgreement',
        'exchange.AssetPair',
        'exchange.ExchangeOrder',
        'exchange.Trade',
        'exchange.TradeHistoryItem',
    ],
)
def test_admin_result_rows_use_one_query(model_label, row_count, django_assert_num_queries):
    expected_labels = {}
    for index in range(row_count):
        obj, labels = _make_admin_row(model_label, index)
        expected_labels[obj.pk] = labels

    request = RequestFactory().get('/admin/')
    request.user = baker.make('users.User', is_staff=True, is_superuser=True)
    model_admin = admin.site._registry[apps.get_model(model_label)]
    changelist = model_admin.get_changelist_instance(request)
    changelist.formset = None

    # Evaluate the actual admin queryset and render every list_display cell, including related object labels.
    with django_assert_num_queries(1):
        rendered = result_list(changelist)

    assert changelist.result_count == row_count
    assert len(rendered['results']) == row_count
    for obj, cells in zip(changelist.result_list, rendered['results'], strict=True):
        row_html = ''.join(cells)
        assert all(label in row_html for label in expected_labels[obj.pk])


@pytest.mark.django_db
def test_trade_string_does_not_fetch_orders(django_assert_num_queries):
    trade, _ = _make_admin_row('exchange.Trade', 0)
    trade = Trade.objects.get(pk=trade.pk)

    with django_assert_num_queries(0):
        label = str(trade)

    assert label == (
        f'Trade ID: {trade.pk} | Buy Order: {trade.buy_order_id} | Sell Order: {trade.sell_order_id} | '
        'Quantity: 5 | Trade Price: 10 | Overpayment Amount: 0'
    )


@pytest.mark.django_db
@pytest.mark.parametrize('row_count', [1, 4])
@pytest.mark.parametrize('ordering', [(), ('-primary_currency__ticker',)])
def test_exchange_order_changelist_including_filter_choices_has_constant_queries(
    row_count, ordering, django_assert_num_queries, monkeypatch
):
    for index in range(row_count):
        _make_admin_row('exchange.ExchangeOrder', index)
    unused_pair = _make_asset_pair(row_count, baker.make('users.User'))
    request = RequestFactory().get('/admin/')
    request.user = baker.make('users.User', is_staff=True, is_superuser=True)
    monkeypatch.setattr(admin.site._registry[AssetPair], 'ordering', ordering)
    model_admin = admin.site._registry[ExchangeOrder]
    field = ExchangeOrder._meta.get_field('asset_pair')
    expected_choices = list(field.get_choices(include_blank=False, ordering=ordering))

    # Both counts, the filter choices, and all result rows, irrespective of distinct asset-pair count.
    with django_assert_num_queries(4):
        changelist = model_admin.get_changelist_instance(request)
        changelist.formset = None
        rendered = result_list(changelist)
        asset_pair_filter = next(spec for spec in changelist.filter_specs if isinstance(spec, AssetPairListFilter))
        choices = list(asset_pair_filter.choices(changelist))

    assert changelist.result_count == row_count
    assert len(rendered['results']) == row_count
    assert asset_pair_filter.lookup_choices == expected_choices
    assert (unused_pair.pk, str(unused_pair)) in asset_pair_filter.lookup_choices
    assert choices[0]['display'] == 'All'
    assert choices[0]['selected']
    assert choices[-1]['display'] == '-'
    assert 'asset_pair__isnull=True' in choices[-1]['query_string']
