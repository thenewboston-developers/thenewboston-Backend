"""Exercise the destructive prototype reset against historical PostgreSQL tables."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from model_bakery import baker

from thenewboston.tribes.models import Tournament
from thenewboston.wallets.models import Wallet

MIGRATION = '0002_replace_seasons_with_tournaments'


@pytest.fixture
def old_game_database(transactional_db):
    executor = MigrationExecutor(connection)
    # Only this empty test database may roll back the irreversible reset. Production
    # cannot reverse a refund or recover discarded game state through migrations.
    reset = executor.loader.get_migration('tribes', MIGRATION)
    reverse_code = reset.operations[0].reverse_code
    reset.operations[0].reverse_code = migrations.RunPython.noop
    try:
        executor.migrate([('tribes', '0001_initial')])
    finally:
        reset.operations[0].reverse_code = reverse_code
    historical = executor.loader.project_state([('tribes', '0001_initial')]).apps
    try:
        yield historical
    finally:
        if 'tribes_season' in connection.introspection.table_names():
            # Failed-reset cases intentionally leave invalid data; remove test data
            # before restoring the schema used by the rest of the suite.
            for name in ('ActionReceipt', 'Activity', 'MoneyEntry', 'Season', 'World'):
                historical.get_model('tribes', name).objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def seed_game(apps):
    user = baker.make('users.User')
    currency = baker.make('currencies.Currency', ticker='TNB')
    wallet = Wallet.objects.create(owner=user, currency=currency, balance=900)
    now = timezone.now()
    game = apps.get_model('tribes', 'Season').objects.create(
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=6),
        status='active',
        currency_id=currency.pk,
        total_deposited=140,
        total_withdrawn=40,
        system_revenue=30,
        state={'tribes': [{'treasury': 50}], 'listings': [{'kind': 'buy', 'quantity': 2, 'price': 10}]},
    )
    entries = apps.get_model('tribes', 'MoneyEntry').objects
    entries.create(season_id=game.pk, wallet_id=wallet.pk, amount=140, reason='deposit')
    entries.create(season_id=game.pk, wallet_id=wallet.pk, amount=-40, reason='withdrawal')
    apps.get_model('tribes', 'ActionReceipt').objects.create(
        season_id=game.pk, actor_id=user.pk, request_id=uuid4(), fingerprint='a' * 64, action='deposit'
    )
    apps.get_model('tribes', 'Activity').objects.create(
        season_id=game.pk, tribe_id=1, user_id=user.pk, text='Old prototype activity'
    )
    apps.get_model('tribes', 'World').objects.create(pk=1)
    return game, wallet


def apply_reset():
    MigrationExecutor(connection).migrate([('tribes', MIGRATION)])


def test_reset_refunds_net_payments_and_replaces_all_old_game_tables(old_game_database):
    _, wallet = seed_game(old_game_database)
    apply_reset()
    wallet.refresh_from_db()
    assert wallet.balance == 1_000
    assert not Tournament.objects.exists()
    with connection.cursor() as cursor:
        for table in ('tribes_activity', 'tribes_actionreceipt', 'tribes_moneyentry', 'tribes_tournamentparticipant'):
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            assert cursor.fetchone()[0] == 0
    assert 'tribes_season' not in connection.introspection.table_names()
    assert 'tribes_world' not in connection.introspection.table_names()
    apply_reset()
    wallet.refresh_from_db()
    assert wallet.balance == 1_000  # Migration retry cannot pay the refund twice.


@pytest.mark.parametrize('invalid_part', ['ledger', 'reserve', 'currency', 'balance_limit', 'wallet_debit'])
def test_reset_refuses_inconsistent_or_unsafe_wallet_changes(old_game_database, invalid_part):
    game, wallet = seed_game(old_game_database)
    if invalid_part == 'ledger':
        game.total_deposited += 1
        game.save()
    elif invalid_part == 'reserve':
        game.system_revenue += 1
        game.save()
    elif invalid_part == 'currency':
        game.currency_id = baker.make('currencies.Currency').pk
        game.save()
    elif invalid_part == 'balance_limit':
        wallet.balance = 9_007_199_254_740_991
        Wallet.objects.filter(pk=wallet.pk).update(balance=wallet.balance)
    else:
        winner = Wallet.objects.create(owner=baker.make('users.User'), currency=wallet.currency, balance=40)
        old_game_database.get_model('tribes', 'MoneyEntry').objects.filter(amount__lt=0).update(wallet_id=winner.pk)
    original = wallet.balance
    with pytest.raises(RuntimeError, match='Tribes reset refused'):
        apply_reset()
    wallet.refresh_from_db()
    assert wallet.balance == original
    assert old_game_database.get_model('tribes', 'Season').objects.filter(pk=game.pk).exists()
    assert old_game_database.get_model('tribes', 'MoneyEntry').objects.count() == 2


def test_reset_allows_a_fresh_install_with_no_old_games(old_game_database):
    apply_reset()
    assert not Tournament.objects.exists()
