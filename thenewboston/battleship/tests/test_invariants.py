"""Money-moving races use independent real PostgreSQL connections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.battleship.models import BattleshipMatch
from thenewboston.battleship.tasks import sweep_battleship_matches
from thenewboston.notifications.models import Notification
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)
BASE = '/api/battleship/matches'


@pytest.fixture(autouse=True)
def no_streaming(monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)
    monkeypatch.setattr(Notification, 'stream', lambda self: None)


def post_as(user, url, data):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(url, data, format='json')


def challenge(host_wallet, guest_wallet, *, request_id=None, stake=100):
    return post_as(
        host_wallet.owner,
        BASE,
        {
            'mode': 'human',
            'opponent_id': guest_wallet.owner_id,
            'stake_amount': stake,
            'request_id': request_id or str(uuid4()),
        },
    )


def pending_match(host_wallet, guest_wallet):
    response = challenge(host_wallet, guest_wallet)
    assert response.status_code == 201, response.data
    return BattleshipMatch.objects.get(pk=response.data['id'])


def act(match, user, action):
    return post_as(user, f'{BASE}/{match.id}/{action}', {'expected_version': match.version})


def concurrent(*actions):
    barrier = Barrier(len(actions))

    def run(action):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return action()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(actions)) as executor:
        futures = [executor.submit(run, action) for action in actions]
        return [future.result(timeout=20) for future in futures]


def assert_conserved(match, host_wallet, guest_wallet):
    match.refresh_from_db()
    host_wallet.refresh_from_db()
    guest_wallet.refresh_from_db()
    escrow = 0 if match.settled else match.prize_pool_total
    assert host_wallet.balance + guest_wallet.balance + escrow == 2000
    assert host_wallet.balance >= 0 and guest_wallet.balance >= 0
    assert (match.ledger_entries.aggregate(total=Sum('amount'))['total'] or 0) == -escrow


def test_duplicate_creates_only_stake_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    request_id = str(uuid4())
    responses = concurrent(
        *[lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet, request_id=request_id) for _ in range(2)]
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].data['id'] == responses[1].data['id']
    match = BattleshipMatch.objects.get(pk=responses[0].data['id'])
    assert match.ledger_entries.count() == 1
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_concurrent_creates_cannot_spend_same_coins_twice(bucky_tnb_wallet, dmitry_tnb_wallet):
    responses = concurrent(*[lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet, stake=600) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [201, 400]
    match = BattleshipMatch.objects.get()
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_simultaneous_cross_challenges_do_not_deadlock(bucky_tnb_wallet, dmitry_tnb_wallet):
    responses = concurrent(
        lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet),
        lambda: challenge(dmitry_tnb_wallet, bucky_tnb_wallet),
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert BattleshipMatch.objects.count() == 2
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (900, 900)


def test_duplicate_accepts_debit_guest_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = pending_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    responses = concurrent(*[lambda: act(match, dmitry_tnb_wallet.owner, 'accept') for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.prize_pool_total == 200
    assert match.ledger_entries.filter(action='stake').count() == 2


def test_accept_cancel_race_conserves_funds(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = pending_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'cancel'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'accept'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    if match.status == 'active':
        assert act(match, bucky_tnb_wallet.owner, 'resign').status_code == 200
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.settled
    assert match.ledger_entries.filter(action__in=['payout', 'refund']).count() == 1


def test_simultaneous_resignations_settle_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = pending_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, dmitry_tnb_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'resign'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'resign'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.ledger_entries.filter(action='payout').count() == 1


def test_placement_abandonment_sweep_race_refunds_both_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = pending_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, dmitry_tnb_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    match.placement_deadline = timezone.now() - timedelta(seconds=1)
    match.save()
    response, _ = concurrent(lambda: act(match, bucky_tnb_wallet.owner, 'resign'), sweep_battleship_matches)
    assert response.status_code in (200, 409)
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.winner is None
    assert match.result_reason == 'placement_abandoned'
    assert match.ledger_entries.filter(action='refund').count() == 2


def test_simultaneous_rematches_create_one_challenge(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = pending_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, dmitry_tnb_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    assert act(match, bucky_tnb_wallet.owner, 'resign').status_code == 200
    match.refresh_from_db()
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'rematch'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'rematch'),
    )
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].data['id'] == responses[1].data['id']
    assert {response.data['your_side'] for response in responses} == {'host', 'guest'}
    rematch = BattleshipMatch.objects.get(rematch_of=match)
    assert rematch.status == 'pending'
    assert rematch.ledger_entries.filter(action='stake').count() == 1
