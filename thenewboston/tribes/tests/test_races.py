"""Exercise PostgreSQL locks with independent connections and real HTTP actions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections, transaction

from thenewboston.tribes.models import ActionReceipt
from thenewboston.tribes.tests.test_integrity import (
    action,
    client_for,
    snapshot,
)
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)


def race(*operations):
    barrier = Barrier(len(operations))

    def run(operation):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return operation()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        futures = [executor.submit(run, operation) for operation in operations]
        return [future.result(timeout=20) for future in futures]


def post_as(user, season, action_name, *, request_id=None, **fields):
    response = client_for(user).post(
        '/api/tribes/actions',
        {'season_id': season.pk, 'request_id': str(request_id or uuid4()), 'action': action_name, **fields},
        format='json',
    )
    return response.status_code, response.data


def test_duplicate_simultaneous_deposits_charge_once(active_game):
    game = active_game
    wallet, season = game['alice_wallet'], game['season']
    request_id = uuid4()
    results = race(
        *[
            lambda: post_as(wallet.owner, season, 'treasury_deposit', amount=600, request_id=request_id)
            for _ in range(2)
        ]
    )
    assert [status for status, data in results] == [200, 200], results
    wallet.refresh_from_db()
    assert wallet.balance == 400
    assert ActionReceipt.objects.filter(actor=wallet.owner, request_id=request_id).count() == 1
    own = next(t for t in snapshot(game['alice'], season)['tribes'] if t['id'] == game['alice_tribe'])
    assert own['treasury'] == 600


def test_distinct_simultaneous_deposits_cannot_spend_same_balance(active_game):
    game = active_game
    wallet, season = game['alice_wallet'], game['season']
    results = race(*[lambda: post_as(wallet.owner, season, 'treasury_deposit', amount=600) for _ in range(2)])
    assert sorted(status for status, data in results) == [200, 400], results
    wallet.refresh_from_db()
    assert wallet.balance == 400


def test_treasury_withdrawals_cannot_duplicate_shared_coins(active_game):
    game = active_game
    wallet, season = game['alice_wallet'], game['season']
    action(game['alice'], season, 'treasury_deposit', amount=600)
    results = race(*[lambda: post_as(wallet.owner, season, 'treasury_withdraw', amount=600) for _ in range(2)])
    assert sorted(status for status, data in results) == [200, 400], results
    wallet.refresh_from_db()
    assert wallet.balance == 1000
    own = next(t for t in snapshot(game['alice'], season)['tribes'] if t['id'] == game['alice_tribe'])
    assert own['treasury'] == 0


def test_game_debit_serializes_with_another_app_wallet_debit(active_game):
    game = active_game
    wallet, season = game['alice_wallet'], game['season']

    def external_debit():
        with transaction.atomic():
            locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
            if locked.balance < 600:
                return 400
            locked.change_balance(-600, should_stream=False)
            return 200

    results = race(
        lambda: post_as(wallet.owner, season, 'treasury_deposit', amount=600)[0],
        external_debit,
    )
    assert sorted(results) == [200, 400]
    wallet.refresh_from_db()
    assert wallet.balance == 400


def test_last_market_stock_cannot_be_sold_to_two_buyers(active_game):
    game = active_game
    season = game['season']
    listing = next(
        entry
        for entry in snapshot(game['alice'], season)['listings']
        if entry['user_id'] is None and entry['item'] == 'timber'
    )
    results = race(
        *[
            lambda user=user: post_as(
                user, season, 'fill_listing', listing_id=listing['id'], quantity=listing['quantity'], account='personal'
            )
            for user in (game['alice_wallet'].owner, game['bob_wallet'].owner)
        ]
    )
    assert sorted(status for status, data in results) == [200, 400], results
    wallets = [game['alice_wallet'], game['bob_wallet']]
    for wallet in wallets:
        wallet.refresh_from_db()
    assert sum(wallet.balance for wallet in wallets) == 2000 - listing['quantity'] * listing['price']
    final = snapshot(game['alice'], season)
    assert all(row['quantity'] == 0 for row in final['listings'] if row['id'] == listing['id'])


def test_buy_order_fill_racing_cancel_cannot_refund_and_pay_same_escrow(active_game):
    game = active_game
    season = game['season']
    season.refresh_from_db()
    season.state['players'][str(game['bob_wallet'].owner_id)]['inventory']['coal'] = 10
    season.save(update_fields=['state'])
    created = action(
        game['alice'], season, 'create_listing', kind='buy', item='coal', quantity=10, price=7, account='personal'
    )
    listing = next(row for row in created['listings'] if row['kind'] == 'buy')
    results = race(
        lambda: post_as(game['alice_wallet'].owner, season, 'cancel_listing', listing_id=listing['id']),
        lambda: post_as(
            game['bob_wallet'].owner, season, 'fill_listing', listing_id=listing['id'], quantity=10, account='personal'
        ),
    )
    assert sorted(status for status, data in results) == [200, 400], results
    for wallet in (game['alice_wallet'], game['bob_wallet']):
        wallet.refresh_from_db()
    assert game['alice_wallet'].balance + game['bob_wallet'].balance == 2000
    assert (game['alice_wallet'].balance, game['bob_wallet'].balance) in [(1000, 1000), (930, 1070)]
    final = snapshot(game['alice'], season)
    assert not any(row['id'] == listing['id'] for row in final['listings'])
    if game['alice_wallet'].balance == 930:
        assert final['viewer']['inventory']['coal'] == 10
