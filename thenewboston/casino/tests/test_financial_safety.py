"""Adversarial tests for the treasury, shared wallets, and recoverable settlement."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from rest_framework.exceptions import ValidationError

from thenewboston.casino import services
from thenewboston.casino.fairness import FairRandom
from thenewboston.casino.models import MAX_SAFE_INTEGER, CasinoBet, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from thenewboston.game_rewards.models import GameFund
from thenewboston.game_rewards.services import contribute
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def no_wallet_streams(monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)


@pytest.fixture
def treasury(bucky_tnb_wallet):
    owner = bucky_tnb_wallet.owner
    owner.is_staff = True
    owner.save(update_fields=['is_staff'])
    Wallet.objects.filter(pk=bucky_tnb_wallet.pk).update(balance=200_000)
    CasinoGameConfig.objects.update_or_create(game='slots', defaults={'enabled': True, 'rules_version': 1})
    CasinoGameConfig.objects.update_or_create(game='roulette', defaults={'enabled': True, 'rules_version': 1})
    services.move_funds(user=owner, amount=100_000, request_id=uuid4(), kind='deposit')
    return owner


def bet_request(user, *, amount=10):
    commitment = services.create_commitment(user=user)
    return {
        'user': user,
        'request_id': uuid4(),
        'commitment_id': commitment.pk,
        'client_seed': 'financial-safety-client',
        'game': 'slots',
        'amount': amount,
    }


def race(*actions):
    barrier = Barrier(len(actions))

    def run(action):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return action()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(actions)) as executor:
        futures = [executor.submit(run, action) for action in actions]
        return [future.result(timeout=20) for future in futures]


def accepted(action):
    try:
        action()
        return True
    except (services.CasinoError, ValidationError):
        return False


def leave_bet_open(payload):
    # Simulate a future interactive game's acceptance boundary. All stake and
    # reservation writes remain real; only immediate completion is deferred.
    with patch.object(services, '_settle_locked', side_effect=lambda **kwargs: kwargs['bet']):
        return services.place_bet(**payload)[0]


def test_concurrent_retry_of_same_wager_charges_and_settles_once(treasury, dmitry_tnb_wallet, monkeypatch):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 0)
    payload = bet_request(dmitry_tnb_wallet.owner)
    results = race(*[lambda: services.place_bet(**payload)[0].pk for _ in range(3)])

    assert len(set(results)) == 1
    assert CasinoBet.objects.count() == 1
    assert CasinoLedgerEntry.objects.filter(kind='stake').count() == 1
    assert CasinoLedgerEntry.objects.filter(kind='payout', amount=0).count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 990
    assert services.reconcile_fund()['balance'] == 100_010


def test_casino_and_board_fund_cannot_spend_same_wallet_coins(treasury, dmitry_tnb_wallet, monkeypatch):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 0)
    Wallet.objects.filter(pk=dmitry_tnb_wallet.pk).update(balance=10)
    payload = bet_request(dmitry_tnb_wallet.owner)

    results = race(
        lambda: accepted(lambda: services.place_bet(**payload)),
        lambda: accepted(lambda: contribute(user=dmitry_tnb_wallet.owner, amount=10, request_id=uuid4())),
    )

    assert sorted(results) == [False, True]
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 0
    board_balance = GameFund.objects.values_list('balance', flat=True).first() or 0
    assert CasinoFund.objects.get().balance + board_balance == 100_010
    services.reconcile_fund()


def test_concurrent_admin_withdrawals_cannot_overdraw(treasury):
    results = race(
        *[
            lambda: accepted(
                lambda: services.move_funds(user=treasury, amount=60_000, request_id=uuid4(), kind='withdrawal')
            )
            for _ in range(2)
        ]
    )

    assert sorted(results) == [False, True]
    assert CasinoFund.objects.get().balance == 40_000
    assert Wallet.objects.get(owner=treasury, currency__ticker='TNB').balance == 160_000
    services.reconcile_fund()


def test_reconciliation_preserves_balances_above_32_bit_integer_range(treasury):
    Wallet.objects.filter(owner=treasury, currency__ticker='TNB').update(balance=4_000_000_000)
    for _ in range(3):
        services.move_funds(user=treasury, amount=1_000_000_000, request_id=uuid4(), kind='deposit')

    report = services.reconcile_fund()
    assert report['balance'] == report['ledger_balance'] == 3_000_100_000


def test_reservations_protect_the_stake_even_after_all_free_funds_are_withdrawn(
    treasury, dmitry_tnb_wallet, monkeypatch
):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 9999)
    bet = leave_bet_open(bet_request(dmitry_tnb_wallet.owner))
    fund = CasinoFund.objects.get()
    assert (fund.balance, fund.reserved, fund.available) == (100_010, 1_000, 99_010)

    with pytest.raises(services.CasinoError):
        services.move_funds(user=treasury, amount=99_011, request_id=uuid4(), kind='withdrawal')
    services.move_funds(user=treasury, amount=99_010, request_id=uuid4(), kind='withdrawal')
    assert services.reconcile_fund()['balance'] == 1_000

    results = race(*[lambda: services.settle_bet(bet_id=bet.pk).payout for _ in range(3)])
    assert results == [1_000, 1_000, 1_000]
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1_990
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert services.reconcile_fund() == {
        'balance': 0,
        'reserved': 0,
        'ledger_balance': 0,
        'expected_reserved': 0,
        'open_bets': 0,
    }


def test_failed_ledger_write_rolls_back_charge_outcome_and_commitment(treasury, dmitry_tnb_wallet, monkeypatch):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 9999)
    payload = bet_request(dmitry_tnb_wallet.owner)
    create = CasinoLedgerEntry.objects.create

    def fail_payout_receipt(**kwargs):
        if kwargs['kind'] == 'payout':
            raise RuntimeError('simulated ledger failure')
        return create(**kwargs)

    with patch.object(CasinoLedgerEntry.objects, 'create', side_effect=fail_payout_receipt):
        with pytest.raises(RuntimeError, match='simulated ledger failure'):
            services.place_bet(**payload)

    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1_000
    assert not CasinoBet.objects.exists()
    assert CasinoLedgerEntry.objects.count() == 1
    assert services.create_commitment(user=dmitry_tnb_wallet.owner).pk == payload['commitment_id']
    assert services.reconcile_fund()['balance'] == 100_000

    services.place_bet(**payload)
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1_990
    services.reconcile_fund()


def test_corrupt_open_result_keeps_reservation_and_cannot_pay(treasury, dmitry_tnb_wallet, monkeypatch):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 0)
    bet = leave_bet_open(bet_request(dmitry_tnb_wallet.owner))
    CasinoBet.objects.filter(pk=bet.pk).update(result={'multiplier': 100})

    with pytest.raises(RuntimeError, match='verification failed'):
        services.settle_bet(bet_id=bet.pk)
    bet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert bet.status == 'open'
    assert dmitry_tnb_wallet.balance == 990
    assert CasinoFund.objects.get().reserved == 1_000
    assert not CasinoLedgerEntry.objects.filter(kind='payout').exists()


def test_closing_casino_and_game_does_not_block_accepted_bet_or_its_retry(treasury, dmitry_tnb_wallet, monkeypatch):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 9999)
    payload = bet_request(dmitry_tnb_wallet.owner)
    bet = leave_bet_open(payload)
    CasinoFund.objects.update(enabled=False)
    CasinoGameConfig.objects.update(enabled=False)

    services.settle_bet(bet_id=bet.pk)
    retry, _, _ = services.place_bet(**payload)
    assert retry.pk == bet.pk and retry.payout == 1_000
    assert CasinoLedgerEntry.objects.filter(bet=bet).count() == 2
    services.reconcile_fund()


@pytest.mark.parametrize('near_limit', ['wallet', 'fund'])
def test_numeric_capacity_is_checked_before_generating_outcome(treasury, dmitry_tnb_wallet, near_limit):
    payload = bet_request(dmitry_tnb_wallet.owner, amount=1)
    if near_limit == 'wallet':
        Wallet.objects.filter(pk=dmitry_tnb_wallet.pk).update(balance=MAX_SAFE_INTEGER)
    else:
        CasinoFund.objects.update(balance=MAX_SAFE_INTEGER)

    with patch.object(FairRandom, 'below', side_effect=AssertionError('must not derive an outcome')) as draw:
        with pytest.raises(services.CasinoError):
            services.place_bet(**payload)
    draw.assert_not_called()
    assert not CasinoBet.objects.exists()
    assert CasinoFund.objects.get().reserved == 0


def test_broadcast_failure_after_commit_does_not_turn_retry_into_second_wager(
    treasury, dmitry_tnb_wallet, monkeypatch, settings
):
    monkeypatch.setattr(FairRandom, 'below', lambda self, bound: 0)
    settings.USE_ON_COMMIT_HOOK = True
    payload = bet_request(dmitry_tnb_wallet.owner)
    with patch.object(Wallet, 'stream', side_effect=RuntimeError('broadcast unavailable')):
        first = services.place_bet(**payload)[0]
        retry = services.place_bet(**payload)[0]
    assert first.pk == retry.pk
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 990
    services.reconcile_fund()
