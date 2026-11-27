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


def post_as(user, tournament, action_name, *, request_id=None, **fields):
    response = client_for(user).post(
        '/api/tribes/actions',
        {'tournament_id': tournament.pk, 'request_id': str(request_id or uuid4()), 'action': action_name, **fields},
        format='json',
    )
    return response.status_code, response.data


def test_duplicate_simultaneous_deposits_charge_once(active_game):
    game = active_game
    wallet, tournament = game['alice_wallet'], game['tournament']
    request_id = uuid4()
    results = race(
        *[
            lambda: post_as(wallet.owner, tournament, 'treasury_deposit', amount=600, request_id=request_id)
            for _ in range(2)
        ]
    )
    assert [status for status, data in results] == [200, 200], results
    wallet.refresh_from_db()
    assert wallet.balance == 400
    assert ActionReceipt.objects.filter(actor=wallet.owner, request_id=request_id).count() == 1
    own = next(t for t in snapshot(game['alice'], tournament)['tribes'] if t['id'] == game['alice_tribe'])
    assert own['treasury'] == 600


def test_distinct_simultaneous_deposits_cannot_spend_same_balance(active_game):
    game = active_game
    wallet, tournament = game['alice_wallet'], game['tournament']
    results = race(*[lambda: post_as(wallet.owner, tournament, 'treasury_deposit', amount=600) for _ in range(2)])
    assert sorted(status for status, data in results) == [200, 400], results
    wallet.refresh_from_db()
    assert wallet.balance == 400


def test_treasury_withdrawals_cannot_duplicate_shared_coins(active_game):
    game = active_game
    wallet, tournament = game['alice_wallet'], game['tournament']
    action(game['alice'], tournament, 'treasury_deposit', amount=600)
    results = race(*[lambda: post_as(wallet.owner, tournament, 'treasury_withdraw', amount=600) for _ in range(2)])
    assert sorted(status for status, data in results) == [200, 400], results
    wallet.refresh_from_db()
    assert wallet.balance == 1000
    own = next(t for t in snapshot(game['alice'], tournament)['tribes'] if t['id'] == game['alice_tribe'])
    assert own['treasury'] == 0


def test_game_debit_serializes_with_another_app_wallet_debit(active_game):
    game = active_game
    wallet, tournament = game['alice_wallet'], game['tournament']

    def external_debit():
        with transaction.atomic():
            locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
            if locked.balance < 600:
                return 400
            locked.change_balance(-600, should_stream=False)
            return 200

    results = race(
        lambda: post_as(wallet.owner, tournament, 'treasury_deposit', amount=600)[0],
        external_debit,
    )
    assert sorted(results) == [200, 400]
    wallet.refresh_from_db()
    assert wallet.balance == 400


def test_last_market_stock_cannot_be_sold_to_two_buyers(active_game):
    game = active_game
    tournament = game['tournament']
    listing = next(
        entry
        for entry in snapshot(game['alice'], tournament)['listings']
        if entry['user_id'] is None and entry['item'] == 'timber'
    )
    results = race(
        *[
            lambda user=user: post_as(
                user,
                tournament,
                'fill_listing',
                listing_id=listing['id'],
                quantity=listing['quantity'],
                account='personal',
            )
            for user in (game['alice_wallet'].owner, game['bob_wallet'].owner)
        ]
    )
    assert sorted(status for status, data in results) == [200, 400], results
    wallets = [game['alice_wallet'], game['bob_wallet']]
    for wallet in wallets:
        wallet.refresh_from_db()
    assert sum(wallet.balance for wallet in wallets) == 2000 - listing['quantity'] * listing['price']
    final = snapshot(game['alice'], tournament)
    assert all(row['quantity'] == 0 for row in final['listings'] if row['id'] == listing['id'])


def test_buy_order_fill_racing_cancel_cannot_refund_and_pay_same_escrow(active_game):
    game = active_game
    tournament = game['tournament']
    tournament.refresh_from_db()
    tournament.state['players'][str(game['bob_wallet'].owner_id)]['inventory']['coal'] = 10
    tournament.save(update_fields=['state'])
    created = action(
        game['alice'], tournament, 'create_listing', kind='buy', item='coal', quantity=10, price=7, account='personal'
    )
    listing = next(row for row in created['listings'] if row['kind'] == 'buy')
    results = race(
        lambda: post_as(game['alice_wallet'].owner, tournament, 'cancel_listing', listing_id=listing['id']),
        lambda: post_as(
            game['bob_wallet'].owner,
            tournament,
            'fill_listing',
            listing_id=listing['id'],
            quantity=10,
            account='personal',
        ),
    )
    assert sorted(status for status, data in results) == [200, 400], results
    for wallet in (game['alice_wallet'], game['bob_wallet']):
        wallet.refresh_from_db()
    assert game['alice_wallet'].balance + game['bob_wallet'].balance == 2000
    assert (game['alice_wallet'].balance, game['bob_wallet'].balance) in [(1000, 1000), (930, 1070)]
    final = snapshot(game['alice'], tournament)
    assert not any(row['id'] == listing['id'] for row in final['listings'])
    if game['alice_wallet'].balance == 930:
        assert final['viewer']['inventory']['coal'] == 10


def test_different_tournaments_cannot_spend_the_same_wallet_balance(active_game):
    from .test_tournaments import activate, another_tournament

    game = active_game
    second = another_tournament(game)
    activate(second)
    results = race(
        lambda: post_as(game['alice_wallet'].owner, game['tournament'], 'treasury_deposit', amount=600),
        lambda: post_as(game['alice_wallet'].owner, second, 'treasury_deposit', amount=600),
    )
    assert sorted(status for status, data in results) == [200, 400], results
    game['alice_wallet'].refresh_from_db()
    assert game['alice_wallet'].balance == 400
    game['tournament'].refresh_from_db()
    second.refresh_from_db()
    assert game['tournament'].total_deposited + second.total_deposited == 600


def test_concurrent_admission_cannot_exceed_capacity(tribes_game):
    from model_bakery import baker
    from rest_framework.exceptions import ValidationError

    from thenewboston.tribes.services import add_participant, update_tournament

    game = tribes_game
    tournament = game['tournament']
    update_tournament(
        tournament.pk, title=tournament.title, starts_at=tournament.starts_at, max_players=3, actor=game['admin']
    )
    users = [baker.make('users.User') for _ in range(2)]

    def admit(user):
        try:
            add_participant(tournament.pk, user.pk, actor=game['admin'])
            return True
        except ValidationError:
            return False

    assert sorted(race(*[lambda user=user: admit(user) for user in users])) == [False, True]
    assert tournament.participants.count() == 3


def test_parallel_tournament_settlement_refunds_shared_wallets_once(active_game):
    from datetime import timedelta

    from django.utils import timezone

    from thenewboston.tribes.services import advance_tournament

    from .test_tournaments import activate, another_tournament

    game = active_game
    second = another_tournament(game)
    activate(second)
    for tournament in (game['tournament'], second):
        action(game['alice'], tournament, 'treasury_deposit', amount=100)
        action(game['bob'], tournament, 'treasury_deposit', amount=200)
        tournament.starts_at = timezone.now() - timedelta(days=8)
        tournament.ends_at = timezone.now() - timedelta(seconds=1)
        tournament.save(update_fields=['starts_at', 'ends_at'])
    race(
        lambda: advance_tournament(game['tournament'].pk),
        lambda: advance_tournament(second.pk),
        lambda: advance_tournament(game['tournament'].pk),
    )
    for tournament in (game['tournament'], second):
        tournament.refresh_from_db()
        assert tournament.status == 'finished'
        assert tournament.total_deposited == tournament.total_withdrawn == 300
        assert tournament.money_entries.filter(reason='tournament_refund').count() == 2
    for wallet in (game['alice_wallet'], game['bob_wallet']):
        wallet.refresh_from_db()
        assert wallet.balance == 1000
