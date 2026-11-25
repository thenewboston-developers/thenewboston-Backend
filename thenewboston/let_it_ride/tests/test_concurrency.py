"""Racing requests against one hand: every decision and every payout happens once."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from django.utils import timezone

from thenewboston.casino import services
from thenewboston.casino.models import CasinoBet, CasinoGameConfig, CasinoLedgerEntry
from thenewboston.let_it_ride import engine
from thenewboston.let_it_ride.services import act, expire_hand
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def no_wallet_streams(monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)


@pytest.fixture
def hand(bucky_tnb_wallet, dmitry_tnb_wallet, monkeypatch):
    owner = bucky_tnb_wallet.owner
    owner.is_staff = True
    owner.save(update_fields=['is_staff'])
    Wallet.objects.filter(pk=bucky_tnb_wallet.pk).update(balance=200_000)
    CasinoGameConfig.objects.update_or_create(
        game='let_it_ride', defaults={'enabled': True, 'rules_version': 1, 'min_bet': 3}
    )
    services.move_funds(user=owner, amount=100_000, request_id=uuid4(), kind='deposit')
    # A pair of tens that becomes three of a kind: every riding bet is paid 3 to 1.
    monkeypatch.setattr(engine, 'deal', lambda random: (['TC', 'TD', '2H'], ['3S', 'TH']))
    player = dmitry_tnb_wallet.owner
    commitment = services.create_commitment(user=player)
    bet, _, _ = services.place_bet(
        user=player,
        request_id=uuid4(),
        commitment_id=commitment.pk,
        client_seed='concurrency-client',
        game='let_it_ride',
        amount=9,
        rules_version=1,
    )
    return bet


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


def attempt(bet, action, revision, action_id=None):
    def run():
        try:
            act(
                user=bet.user,
                request_id=bet.request_id,
                action_id=action_id or uuid4(),
                action=action,
                expected_revision=revision,
            )
            return 'accepted'
        except services.CasinoError as error:
            return error.data['code']

    return run


def test_two_different_decisions_for_the_same_bet_cannot_both_apply(hand):
    results = race(attempt(hand, 'ride', 0), attempt(hand, 'pull', 0), attempt(hand, 'pull', 0))
    assert sorted(results) == ['accepted', 'revision_conflict', 'revision_conflict']
    hand.refresh_from_db()
    assert len(hand.result['decisions']) == 1 and hand.status == 'open'
    assert services.reconcile_fund()['open_bets'] == 1


def test_a_repeated_final_decision_pays_once(hand):
    act(user=hand.user, request_id=hand.request_id, action_id=uuid4(), action='ride', expected_revision=0)
    action_id = uuid4()
    results = race(*[attempt(hand, 'ride', 1, action_id) for _ in range(4)])
    assert results == ['accepted'] * 4
    hand.refresh_from_db()
    assert (hand.status, hand.payout) == ('settled', 36)
    assert CasinoLedgerEntry.objects.filter(bet=hand, kind='payout').count() == 1
    assert Wallet.objects.get(owner=hand.user).balance == 1_000 - 9 + 36
    assert services.reconcile_fund() == {
        'balance': 100_000 + 9 - 36,
        'reserved': 0,
        'ledger_balance': 100_000 + 9 - 36,
        'expected_reserved': 0,
        'open_bets': 0,
    }


def test_the_timeout_sweep_and_a_late_decision_settle_the_hand_once(hand):
    CasinoBet.objects.filter(pk=hand.pk).update(
        created_date=timezone.now() - timedelta(seconds=engine.TIMEOUT_SECONDS + 1)
    )
    results = race(
        attempt(hand, 'pull', 0),
        lambda: expire_hand(bet_id=hand.pk).status,
        lambda: expire_hand(bet_id=hand.pk).status,
    )
    # Whoever gets the lock first times the hand out; the late decision is never applied.
    assert results[0] in ('accepted', 'hand_settled')
    assert results[1:] == ['settled', 'settled']
    hand.refresh_from_db()
    assert (hand.settlement_reason, hand.result['decisions']) == ('timeout', ['ride', 'ride'])
    assert hand.payout == 36
    assert CasinoLedgerEntry.objects.filter(bet=hand, kind='payout').count() == 1
    assert services.reconcile_fund()['reserved'] == 0
