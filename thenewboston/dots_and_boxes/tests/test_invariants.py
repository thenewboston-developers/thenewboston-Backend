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

from thenewboston.dots_and_boxes.models import DotsAndBoxesMatch
from thenewboston.dots_and_boxes.tasks import sweep_dots_and_boxes_matches
from thenewboston.notifications.models import Notification
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)
BASE = '/api/dots-and-boxes/matches'


@pytest.fixture(autouse=True)
def no_streaming(monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)
    monkeypatch.setattr(Notification, 'stream', lambda self: None)


def post_as(user, url, data):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(url, data, format='json')


def challenge(blue_wallet, red_wallet, *, request_id=None, stake=100):
    return post_as(
        blue_wallet.owner,
        BASE,
        {
            'mode': 'human',
            'opponent_id': red_wallet.owner_id,
            'stake_amount': stake,
            'request_id': request_id or str(uuid4()),
        },
    )


def pending_match(blue_wallet, red_wallet):
    response = challenge(blue_wallet, red_wallet)
    assert response.status_code == 201, response.data
    return DotsAndBoxesMatch.objects.get(pk=response.data['id'])


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


def assert_conserved(match, blue_wallet, red_wallet):
    match.refresh_from_db()
    blue_wallet.refresh_from_db()
    red_wallet.refresh_from_db()
    escrow = 0 if match.settled else match.prize_pool_total
    assert blue_wallet.balance + red_wallet.balance + escrow == 2000
    assert blue_wallet.balance >= 0 and red_wallet.balance >= 0
    assert (match.ledger_entries.aggregate(total=Sum('amount'))['total'] or 0) == -escrow


def test_duplicate_creates_only_stake_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    request_id = str(uuid4())
    responses = concurrent(
        *[lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet, request_id=request_id) for _ in range(2)]
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].data['id'] == responses[1].data['id']
    match = DotsAndBoxesMatch.objects.get(pk=responses[0].data['id'])
    assert match.ledger_entries.count() == 1
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_concurrent_creates_cannot_spend_same_coins_twice(bucky_tnb_wallet, dmitry_tnb_wallet):
    responses = concurrent(*[lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet, stake=600) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [201, 400]
    match = DotsAndBoxesMatch.objects.get()
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)


def test_simultaneous_cross_challenges_do_not_deadlock(bucky_tnb_wallet, dmitry_tnb_wallet):
    responses = concurrent(
        lambda: challenge(bucky_tnb_wallet, dmitry_tnb_wallet),
        lambda: challenge(dmitry_tnb_wallet, bucky_tnb_wallet),
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert DotsAndBoxesMatch.objects.count() == 2
    bucky_tnb_wallet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert (bucky_tnb_wallet.balance, dmitry_tnb_wallet.balance) == (900, 900)


def test_duplicate_accepts_debit_red_once(bucky_tnb_wallet, dmitry_tnb_wallet):
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


def test_timeout_sweep_racing_resignation_settles_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = pending_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, dmitry_tnb_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    match.turn_started_at = timezone.now() - timedelta(seconds=1000)
    match.save()
    response, _ = concurrent(lambda: act(match, bucky_tnb_wallet.owner, 'resign'), sweep_dots_and_boxes_matches)
    assert response.status_code in (200, 409)
    assert_conserved(match, bucky_tnb_wallet, dmitry_tnb_wallet)
    assert match.winner == 'red'
    assert match.result_reason == 'timeout'
    assert match.ledger_entries.filter(action='payout').count() == 1


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
    assert {response.data['your_side'] for response in responses} == {'blue', 'red'}
    rematch = DotsAndBoxesMatch.objects.get(rematch_of=match)
    assert rematch.status == 'pending'
    assert rematch.ledger_entries.filter(action='stake').count() == 1


def test_duplicate_winning_lines_pay_computer_reward_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    from thenewboston.dots_and_boxes.tests.test_matches import one_line_left
    from thenewboston.game_rewards.models import GameFund, GameRewardDecision
    from thenewboston.game_rewards.services import contribute

    contribute(user=dmitry_tnb_wallet.owner, amount=20, request_id=uuid4())
    response = post_as(bucky_tnb_wallet.owner, BASE, {'mode': 'computer', 'board_size': 3, 'request_id': str(uuid4())})
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    last = one_line_left(match, blue=4, red=4)
    responses = concurrent(
        *[
            lambda: post_as(
                bucky_tnb_wallet.owner,
                f'{BASE}/{match.id}/move',
                {'expected_version': match.version, 'line': last},
            )
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 1010 and GameFund.objects.get().balance == 10
    assert GameRewardDecision.objects.filter(game='dots_and_boxes', match_id=match.id).count() == 1


def test_duplicate_lines_are_drawn_and_scored_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    match = pending_match(bucky_tnb_wallet, dmitry_tnb_wallet)
    assert act(match, dmitry_tnb_wallet.owner, 'accept').status_code == 200
    match.refresh_from_db()
    # Three sides of the top-left box are drawn; both requests draw the fourth.
    match.lines = [1 if line in (0, 4, 20) else 0 for line in range(40)]
    match.save()
    responses = concurrent(
        *[
            lambda: post_as(
                bucky_tnb_wallet.owner,
                f'{BASE}/{match.id}/move',
                {'expected_version': match.version, 'line': 21},
            )
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    match.refresh_from_db()
    assert match.score_blue == 1 and match.moves == [21] and match.boxes[0] == 1


def test_computer_turn_racing_a_resignation_settles_once(bucky_tnb_wallet):
    from thenewboston.dots_and_boxes.services import run_computer

    response = post_as(bucky_tnb_wallet.owner, BASE, {'mode': 'computer', 'request_id': str(uuid4())})
    match = DotsAndBoxesMatch.objects.get(pk=response.data['id'])
    match.active_side = 'red'
    match.save()
    resignation, _ = concurrent(
        lambda: act(match, bucky_tnb_wallet.owner, 'resign'),
        lambda: run_computer(match.id, match.version),
    )
    # Either the resignation lands first, or the computer moves first and the resignation is stale.
    assert resignation.status_code in (200, 409)
    match.refresh_from_db()
    if resignation.status_code == 200:
        assert match.status == 'finished' and match.winner == 'red' and match.moves == []
    else:
        assert match.status == 'active' and len(match.moves) == 1
    assert match.events.count() == match.version
