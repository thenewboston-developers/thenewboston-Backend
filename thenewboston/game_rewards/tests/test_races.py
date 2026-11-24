from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from rest_framework.exceptions import ValidationError

from thenewboston.game_rewards.models import GameFund, GameFundDeposit, GameRewardDecision
from thenewboston.game_rewards.services import contribute, settle_computer_reward
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def no_streams(monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)


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


def test_simultaneous_winners_cannot_overdraw_last_reward(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=uuid4())
    results = race(
        *[
            lambda game=game: settle_computer_reward(
                game=game, match_id=1, user_id=dmitry_tnb_wallet.owner_id, won=True
            )
            for game in ['backgammon', 'battleship', 'connect_five']
        ]
    )
    assert sorted(result['amount'] for result in results) == [0, 0, 10]
    assert GameFund.objects.get().balance == 0
    assert GameRewardDecision.objects.count() == 3
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1010


def test_same_reward_racing_is_paid_once(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=20, request_id=uuid4())
    results = race(
        *[
            lambda: settle_computer_reward(game='battleship', match_id=1, user_id=dmitry_tnb_wallet.owner_id, won=True)
            for _ in range(2)
        ]
    )
    assert [result['amount'] for result in results] == [10, 10]
    assert GameFund.objects.get().balance == 10
    assert GameRewardDecision.objects.count() == 1


def test_deposit_races_share_fund_lock_and_never_double_spend(bucky_tnb_wallet):
    request_id = uuid4()
    results = race(
        *[lambda: contribute(user=bucky_tnb_wallet.owner, amount=600, request_id=request_id)[0].id for _ in range(2)]
    )
    assert results[0] == results[1]
    assert GameFundDeposit.objects.count() == 1
    assert GameFund.objects.get().balance == 600
    bucky_tnb_wallet.refresh_from_db()
    assert bucky_tnb_wallet.balance == 400


def test_distinct_contributions_cannot_spend_same_coins(bucky_tnb_wallet):
    def deposit():
        try:
            contribute(user=bucky_tnb_wallet.owner, amount=600, request_id=uuid4())
            return 'paid'
        except ValidationError:
            return 'insufficient'

    assert sorted(race(deposit, deposit)) == ['insufficient', 'paid']
    assert GameFund.objects.get().balance == 600


def test_contribution_and_reward_on_same_wallet_do_not_deadlock(bucky_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=uuid4())
    race(
        lambda: contribute(user=bucky_tnb_wallet.owner, amount=10, request_id=uuid4()),
        lambda: settle_computer_reward(game='backgammon', match_id=1, user_id=bucky_tnb_wallet.owner_id, won=True),
    )
    bucky_tnb_wallet.refresh_from_db()
    fund = GameFund.objects.get()
    assert bucky_tnb_wallet.balance + fund.balance == 1000
    assert fund.total_deposited - fund.total_paid == fund.balance == 10
