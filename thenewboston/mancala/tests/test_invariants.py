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

from thenewboston.mancala.models import MancalaMatch
from thenewboston.mancala.tasks import sweep_mancala_matches
from thenewboston.notifications.models import Notification
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)
BASE = '/api/mancala/matches'


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
    return MancalaMatch.objects.get(pk=response.data['id'])


def active_match(host_wallet, guest_wallet):
    match = pending_match(host_wallet, guest_wallet)
    assert act(match, guest_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    return match


def act(match, user, action, **data):
    return post_as(user, f'{BASE}/{match.id}/{action}', {'expected_version': match.version, **data})


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
    match = MancalaMatch.objects.get(pk=responses[0].data['id'])
    assert match.ledger_entries.count() == 1
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_concurrent_creates_cannot_spend_same_coins_twice(bucky_tnb_wallet, dmitry_tnb_wallet):
    responses = concurrent(*[lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet, stake=600) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [201, 400]
    match = MancalaMatch.objects.get()
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_simultaneous_cross_challenges_do_not_deadlock(bucky_tnb_wallet, dmitry_tnb_wallet):
    responses = concurrent(
        lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet),
        lambda: challenge(dmitry_tnb_wallet, bucky_tnb_wallet),
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert MancalaMatch.objects.count() == 2
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


def test_accept_expiry_sweep_race_conserves_funds(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = pending_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    match.expires_at = timezone.now() - timedelta(seconds=1)
    match.save()
    response, _ = concurrent(lambda: act(match, dmitry_tnb_wallet.owner, 'accept'), sweep_mancala_matches)
    assert response.status_code in (200, 409)
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.status == 'expired'
    assert match.ledger_entries.filter(action='refund').count() == 1
    assert not match.ledger_entries.filter(wallet=dmitry_tnb_wallet).exists()


def test_simultaneous_resignations_settle_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'resign'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'resign'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.ledger_entries.filter(action='payout').count() == 1


def test_duplicate_moves_sow_one_pit(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    mover = match.host if match.active_side == 'host' else match.guest
    responses = concurrent(*[lambda: act(match, mover, 'move', pit=0) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [200, 409]
    match.refresh_from_db()
    assert match.events.filter(event_type='move').count() == 1
    assert sum(match.board) == 48
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_winning_move_and_resignation_race_pays_one_prize(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    # The host's last stone ends the game 27 to 21.
    match.board = [0, 0, 0, 0, 0, 1, 26, 1, 2, 3, 0, 0, 0, 15]
    match.active_side = 'host'
    match.save()
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'move', pit=5),
        lambda: act(match, dmitry_tnb_wallet.owner, 'resign'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.winner == 'host'
    assert match.ledger_entries.filter(action='payout').count() == 1
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1100


def test_drawn_last_move_and_timeout_sweep_race_settle_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    # The host's last stone ends the game 24 all, but the host's clock has already run out.
    match.board = [0, 0, 0, 0, 0, 1, 23, 1, 2, 0, 0, 0, 0, 21]
    match.active_side = 'host'
    match.clock_host_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()
    response, _ = concurrent(lambda: act(match, bucky_tnb_wallet.owner, 'move', pit=5), sweep_mancala_matches)
    assert response.status_code in (200, 409)
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert (match.winner, match.result_reason) == ('guest', 'timeout')
    assert match.ledger_entries.filter(action='payout').count() == 1
    assert not match.ledger_entries.filter(action='refund').exists()


def test_reads_racing_an_expired_clock_settle_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    match.active_side = 'host'
    match.clock_host_ms = 1
    match.turn_started_at = timezone.now() - timedelta(seconds=1)
    match.save()

    def read():
        return APIClient().get(f'{BASE}/{match.id}')

    responses = concurrent(read, read, read)
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert {response.data['status'] for response in responses} == {'finished'}
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.events.filter(event_type='timeout').count() == 1
    assert match.ledger_entries.filter(action='payout').count() == 1


def test_simultaneous_rematches_create_one_challenge(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, bucky_tnb_wallet.owner, 'resign').status_code == 200
    match.refresh_from_db()
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'rematch'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'rematch'),
    )
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].data['id'] == responses[1].data['id']
    assert {response.data['your_side'] for response in responses} == {'host', 'guest'}
    rematch = MancalaMatch.objects.get(rematch_of=match)
    assert rematch.status == 'pending'
    assert rematch.ledger_entries.filter(action='stake').count() == 1
