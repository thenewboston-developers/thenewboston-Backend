from datetime import timedelta
from importlib import import_module
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.casino import services
from thenewboston.casino.fairness import FairRandom, seed_hash
from thenewboston.casino.models import CasinoBet, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from thenewboston.casino.tasks import reconcile_casino
from thenewboston.plinko.rules import PLINKO_V1
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db


@pytest.fixture
def funded(bucky_tnb_wallet, monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)
    owner = bucky_tnb_wallet.owner
    owner.is_staff = True
    owner.save(update_fields=['is_staff'])
    Wallet.objects.filter(pk=bucky_tnb_wallet.pk).update(balance=200_000)
    CasinoGameConfig.objects.update_or_create(game='plinko', defaults={'enabled': True, 'rules_version': 1})
    services.move_funds(user=owner, amount=100_000, request_id=uuid4(), kind='deposit')
    return owner


def wager(user, **changes):
    commitment = services.create_commitment(user=user)
    return {
        'user': user,
        'request_id': uuid4(),
        'commitment_id': commitment.pk,
        'client_seed': 'plinko-test-client',
        'game': 'plinko',
        'amount': 20,
        'rules_version': 1,
        **changes,
    }


def test_catalog_and_api_return_a_verifiable_idempotent_receipt(funded):
    client = APIClient()
    game = next(game for game in client.get('/api/casino').data['games'] if game['id'] == 'plinko')
    assert game['available'] and game['enabled']
    assert (game['max_bet'], game['max_multiplier'], game['rows']) == (20, 50, 12)
    assert game['house_edge'] == 1 - 3898 / 4096
    client.force_authenticate(funded)
    payload = wager(funded)
    del payload['user']
    response = client.post('/api/casino/bets', payload, format='json')
    assert response.status_code == 201
    receipt = response.data
    fairness = receipt['fairness']
    assert receipt['status'] == 'settled'
    assert receipt['selection'] == {}
    assert seed_hash(fairness['server_seed']) == fairness['server_seed_hash']
    random = FairRandom(
        server_seed=fairness['server_seed'],
        client_seed=fairness['client_seed'],
        commitment_id=fairness['commitment_id'],
        game='plinko',
        rules_version=1,
    )
    assert receipt['result'] == PLINKO_V1.outcome(random, {})
    assert receipt['payout'] == 20 * receipt['result']['multiplier']
    assert receipt['wallet_balance'] == 100_000 - 20 + receipt['payout']
    assert receipt['profit'] == receipt['payout'] - 20
    assert client.get(f'/api/casino/bets/{receipt["request_id"]}').data['result'] == receipt['result']
    assert client.get('/api/casino/bets').data[0]['id'] == receipt['id']
    CasinoGameConfig.objects.filter(game='plinko').update(enabled=False)
    repeated = client.post('/api/casino/bets', payload, format='json')
    assert repeated.status_code == 201 and repeated.data['id'] == receipt['id']
    assert repeated.data['wallet_balance'] == receipt['wallet_balance']
    assert CasinoLedgerEntry.objects.filter(bet_id=receipt['id']).count() == 2
    changed = client.post('/api/casino/bets', {**payload, 'amount': 19}, format='json')
    assert changed.status_code == 409
    assert services.reconcile_fund()['reserved'] == 0


@pytest.mark.parametrize('draw,slot,multiplier', [(0, 0, 50), (4095, 12, 50), (63, 6, 0), (15, 4, 1)])
def test_extreme_and_center_paths_pay_exact_whole_tnb(funded, monkeypatch, draw, slot, multiplier):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: draw)
    bet, fund, wallet = services.place_bet(**wager(funded))
    assert bet.result['slot'] == slot
    assert bet.payout == 20 * multiplier
    assert bet.house_exposure == 980
    assert wallet.balance == 99_980 + bet.payout
    assert fund.balance == 100_020 - bet.payout
    assert services.reconcile_fund()['reserved'] == 0


@pytest.mark.parametrize('changes', [{'amount': 21}, {'selection': {'slot': 0}}, {'rules_version': 2}])
def test_invalid_or_over_limit_wagers_do_not_charge_or_derive_a_path(funded, changes):
    payload = wager(funded, **changes)
    with patch.object(FairRandom, 'below', side_effect=AssertionError('must reject before drawing')) as draw:
        with pytest.raises(services.CasinoError):
            services.place_bet(**payload)
    draw.assert_not_called()
    assert not CasinoBet.objects.exists()
    assert services.reconcile_fund()['balance'] == 100_000
    assert Wallet.objects.get(owner=funded, currency__ticker='TNB').balance == 100_000


def test_background_recovery_keeps_the_persisted_path_and_protects_maximum_payout(funded, monkeypatch):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 0)
    with patch.object(services, '_settle_locked', side_effect=lambda **kwargs: kwargs['bet']):
        bet, fund, _ = services.place_bet(**wager(funded))
    persisted_result = bet.result
    assert (fund.balance, fund.reserved, fund.available) == (100_020, 1000, 99_020)
    with pytest.raises(services.CasinoError):
        services.move_funds(user=funded, amount=99_021, request_id=uuid4(), kind='withdrawal')
    services.move_funds(user=funded, amount=99_020, request_id=uuid4(), kind='withdrawal')
    CasinoBet.objects.filter(pk=bet.pk).update(created_date=timezone.now() - timedelta(minutes=1))
    CasinoGameConfig.objects.filter(game='plinko').update(enabled=False)
    assert reconcile_casino()['reserved'] == 0
    bet.refresh_from_db()
    assert bet.result == persisted_result
    assert bet.status == 'settled' and bet.payout == 1000
    assert services.settle_bet(bet_id=bet.pk).payout == 1000
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert services.reconcile_fund()['balance'] == 0


def test_background_recovery_never_pays_a_tampered_path(funded, monkeypatch):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 0)
    with patch.object(services, '_settle_locked', side_effect=lambda **kwargs: kwargs['bet']):
        bet, _, _ = services.place_bet(**wager(funded))
    # The pocket/payout still look correct, but a changed path must fail full-result verification.
    CasinoBet.objects.filter(pk=bet.pk).update(result={**bet.result, 'path': [1] * 12})
    with pytest.raises(RuntimeError, match='verification failed'):
        services.settle_bet(bet_id=bet.pk)
    bet.refresh_from_db()
    assert bet.status == 'open'
    assert CasinoFund.objects.get(pk=1).reserved == 1000
    assert not CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').exists()
    assert services.reconcile_fund()['reserved'] == 1000


def test_configuration_migration_never_funds_game_or_overwrites_admin_settings(funded):
    migration = import_module('thenewboston.casino.migrations.0004_plinko')
    CasinoGameConfig.objects.filter(game='plinko').delete()
    before = services.reconcile_fund()
    ledger_count = CasinoLedgerEntry.objects.count()
    migration.configure_plinko(apps, None)
    config = CasinoGameConfig.objects.get(game='plinko')
    assert (config.enabled, config.rules_version, config.min_bet) == (True, 1, 1)
    CasinoGameConfig.objects.filter(game='plinko').update(enabled=False, min_bet=5)
    migration.configure_plinko(apps, None)
    config.refresh_from_db()
    assert not config.enabled and config.min_bet == 5
    assert services.reconcile_fund() == before
    assert CasinoLedgerEntry.objects.count() == ledger_count
