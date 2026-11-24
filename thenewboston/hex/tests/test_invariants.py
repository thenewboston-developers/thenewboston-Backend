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

from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.game_rewards.services import contribute
from thenewboston.hex.models import HexMatch
from thenewboston.hex.rules import BLUE, RED
from thenewboston.hex.tasks import sweep_hex_matches
from thenewboston.hex.tests.test_rules import board_with, column, row_cells
from thenewboston.notifications.models import Notification
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)
BASE = '/api/hex/matches'
SIZE = 7


@pytest.fixture(autouse=True)
def no_streaming(monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)
    monkeypatch.setattr(Notification, 'stream', lambda self: None)


def post_as(user, url, data):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(url, data, format='json')


def challenge(red_wallet, blue_wallet, *, request_id=None, stake=100):
    return post_as(
        red_wallet.owner,
        BASE,
        {
            'mode': 'human',
            'opponent_id': blue_wallet.owner_id,
            'stake_amount': stake,
            'board_size': SIZE,
            'request_id': request_id or str(uuid4()),
        },
    )


def pending_match(red_wallet, blue_wallet):
    response = challenge(red_wallet, blue_wallet)
    assert response.status_code == 201, response.data
    return HexMatch.objects.get(pk=response.data['id'])


def active_match(red_wallet, blue_wallet):
    match = pending_match(red_wallet, blue_wallet)
    assert act(match, blue_wallet.owner, 'accept').status_code == 200
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


def assert_conserved(match, red_wallet, blue_wallet):
    match.refresh_from_db()
    red_wallet.refresh_from_db()
    blue_wallet.refresh_from_db()
    escrow = 0 if match.settled else match.prize_pool_total
    assert red_wallet.balance + blue_wallet.balance + escrow == 2000
    assert red_wallet.balance >= 0 and blue_wallet.balance >= 0
    assert (match.ledger_entries.aggregate(total=Sum('amount'))['total'] or 0) == -escrow


def test_duplicate_creates_only_stake_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    request_id = str(uuid4())
    responses = concurrent(
        *[lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet, request_id=request_id) for _ in range(2)]
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].data['id'] == responses[1].data['id']
    match = HexMatch.objects.get(pk=responses[0].data['id'])
    assert match.ledger_entries.count() == 1
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_concurrent_creates_cannot_spend_same_coins_twice(bucky_tnb_wallet, dmitry_tnb_wallet):
    responses = concurrent(*[lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet, stake=600) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [201, 400]
    match = HexMatch.objects.get()
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_simultaneous_cross_challenges_do_not_deadlock(bucky_tnb_wallet, dmitry_tnb_wallet):
    responses = concurrent(
        lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet),
        lambda: challenge(dmitry_tnb_wallet, bucky_tnb_wallet),
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert HexMatch.objects.count() == 2
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (900, 900)


def test_duplicate_accepts_debit_blue_once(bucky_tnb_wallet, dmitry_tnb_wallet):
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
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    responses = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'resign'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'resign'),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.ledger_entries.filter(action='payout').count() == 1


def test_timeout_sweep_racing_resignation_settles_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    match.turn_started_at = timezone.now() - timedelta(seconds=1000)
    match.save()
    response, _ = concurrent(lambda: act(match, bucky_tnb_wallet.owner, 'resign'), sweep_hex_matches)
    assert response.status_code in (200, 409)
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.winner == 'blue'
    assert match.result_reason == 'timeout'
    assert match.ledger_entries.filter(action='payout').count() == 1


def test_duplicate_winning_moves_pay_the_prize_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    match.board = board_with(SIZE, red=column(SIZE, 3, range(SIZE - 1)), blue=row_cells(SIZE, SIZE - 1, range(2)))
    match.move_count = SIZE + 1
    match.save()
    cell = (SIZE - 1) * SIZE + 3
    responses = concurrent(*[lambda: act(match, bucky_tnb_wallet.owner, 'move', cell=cell) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert (match.winner, match.result_reason) == ('red', 'connection')
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (1100, 900)
    assert match.ledger_entries.filter(action='payout').count() == 1


def test_swap_racing_a_stone_keeps_one_reply_to_the_opening(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = active_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, bucky_tnb_wallet.owner, 'move', cell=2 * SIZE + 4).status_code == 200
    match.refresh_from_db()
    responses = concurrent(
        lambda: act(match, dmitry_tnb_wallet.owner, 'swap'),
        lambda: act(match, dmitry_tnb_wallet.owner, 'move', cell=0),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    match.refresh_from_db()
    assert match.move_count == 2 and match.active_side == 'red'
    # Either the opening stone changed hands, or it stayed red and Blue added a stone: never both.
    assert (match.board.count(RED), match.board.count(BLUE)) in {(0, 1), (1, 1)}
    assert match.board.count(RED) == (0 if match.last_move['swap'] else 1)
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


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
    assert {response.data['your_side'] for response in responses} == {'red', 'blue'}
    rematch = HexMatch.objects.get(rematch_of=match)
    assert rematch.status == 'pending' and rematch.board_size == SIZE
    assert rematch.ledger_entries.filter(action='stake').count() == 1


def test_duplicate_winning_moves_pay_computer_reward_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = post_as(
        bucky_tnb_wallet.owner, BASE, {'mode': 'computer', 'board_size': SIZE, 'request_id': str(uuid4())}
    )
    match = HexMatch.objects.get(pk=response.data['id'])
    match.board = board_with(SIZE, red=column(SIZE, 3, range(SIZE - 1)), blue=row_cells(SIZE, SIZE - 1, range(2)))
    match.move_count = SIZE + 1
    match.save()
    cell = (SIZE - 1) * SIZE + 3
    responses = concurrent(*[lambda: act(match, bucky_tnb_wallet.owner, 'move', cell=cell) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [200, 409]
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010 and GameFund.objects.get().balance == 10
    assert GameRewardDecision.objects.filter(game='hex', match_id=match.id).count() == 1
