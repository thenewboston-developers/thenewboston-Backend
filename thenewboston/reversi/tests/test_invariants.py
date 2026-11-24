"""Exercise money-moving races with separate PostgreSQL connections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.reversi.models import ReversiLedgerEntry, ReversiMatch
from thenewboston.reversi.tasks import sweep_reversi_matches
from thenewboston.reversi.tests.test_rules import full_board
from thenewboston.wallets.models import Wallet

BASE = '/api/reversi/matches'
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def no_wallet_network(monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)


def post_as(user, url, data):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(url, data, format='json')


def challenge(black_wallet, white_wallet):
    response = post_as(
        black_wallet.owner,
        BASE,
        {
            'mode': 'human',
            'opponent_id': white_wallet.owner_id,
            'color': 'black',
            'stake_amount': 100,
            'request_id': str(uuid4()),
        },
    )
    assert response.status_code == 201, response.data
    return ReversiMatch.objects.get(pk=response.data['id'])


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
        return [future.result(timeout=15) for future in futures]


def act(match, user, action, version=None, **data):
    return post_as(
        user, f'{BASE}/{match.id}/{action}', {'expected_version': match.version if version is None else version, **data}
    )


def assert_conserved(match, black_wallet, white_wallet):
    match.refresh_from_db()
    black_wallet.refresh_from_db()
    white_wallet.refresh_from_db()
    escrow = 0 if match.settled else match.prize_pool_total
    assert black_wallet.balance + white_wallet.balance + escrow == 2000
    assert black_wallet.balance >= 0 and white_wallet.balance >= 0
    ledger_total = ReversiLedgerEntry.objects.filter(match=match).aggregate(total=Sum('amount'))['total'] or 0
    assert ledger_total == -escrow


def test_duplicate_create_requests_lock_one_stake(bucky_tnb_wallet, dmitry_tnb_wallet):
    payload = {
        'mode': 'human',
        'opponent_id': dmitry_tnb_wallet.owner_id,
        'stake_amount': 100,
        'request_id': str(uuid4()),
    }
    responses = concurrent(*[lambda: post_as(bucky_tnb_wallet.owner, BASE, payload)] * 2)
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].data['id'] == responses[1].data['id']
    match = ReversiMatch.objects.get()
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.ledger_entries.count() == 1


def test_duplicate_accept_requests_only_lock_one_opponent_stake(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = challenge(bucky_tnb_wallet, dmitry_tnb_wallet)
    responses = concurrent(
        lambda: act(match, dmitry_tnb_wallet.owner, 'accept'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'accept'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.prize_pool_total == 200
    assert match.status == 'active'
    assert match.ledger_entries.filter(action='stake').count() == 2
    assert match.events.filter(event_type='accepted').count() == 1


def test_simultaneous_resignations_settle_the_pool_only_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = challenge(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, dmitry_tnb_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'resign'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'resign'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.settled and match.status == 'finished'
    payout = match.ledger_entries.get(action='payout')
    assert payout.amount == 200
    assert payout.wallet.owner_id == (match.host_id if match.winner == 'black' else match.guest_id)
    assert match.events.filter(event_type='resign').count() == 1


def test_accept_cancel_race_and_stale_retries_conserve_coins(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = challenge(bucky_tnb_wallet, dmitry_tnb_wallet)
    original_version = match.version
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'cancel'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'accept'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    if match.status == 'active':
        assert act(match, bucky_tnb_wallet.owner, 'resign').status_code == 200
    else:
        assert match.status == 'cancelled'
    for action, user in (
        ('accept', dmitry_tnb_wallet.owner),
        ('cancel', bucky_tnb_wallet.owner),
        ('resign', bucky_tnb_wallet.owner),
    ):
        assert act(match, user, action, original_version).status_code == 409
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.settled
    assert match.ledger_entries.filter(action__in=['payout', 'refund']).count() == 1


def test_final_move_racing_with_resignation_pays_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = challenge(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, dmitry_tnb_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    match.board = full_board(5)
    match.save()
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'move', row=0, column=0),
        lambda: act(match, dmitry_tnb_wallet.owner, 'resign'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert (match.status, match.winner) == ('finished', 'black')
    assert match.ledger_entries.filter(action='payout').count() == 1
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1100


def test_timeout_sweep_racing_with_resignation_pays_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = challenge(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, dmitry_tnb_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    match.clock_black_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    response, _ = concurrent(
        lambda: act(match, dmitry_tnb_wallet.owner, 'resign'),
        lambda: sweep_reversi_matches(),
    )
    assert response.status_code in (200, 409)
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.winner == 'white'
    assert match.result_reason == 'timeout'
    assert match.ledger_entries.filter(action='payout').count() == 1
    assert match.events.filter(event_type='timeout').count() == 1
