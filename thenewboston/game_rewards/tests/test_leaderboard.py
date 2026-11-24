from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from model_bakery import baker
from rest_framework.test import APIClient

from thenewboston.game_rewards.models import GameFund, GameRewardDecision
from thenewboston.game_rewards.services import contribute, settle_computer_reward
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db

URL = '/api/game-rewards/leaderboard'
GAMES = [game for game, _ in GameRewardDecision._meta.get_field('game').choices]


def pay(wallet, *, game='battleship', match_id=1):
    return settle_computer_reward(game=game, match_id=match_id, user_id=wallet.owner_id, won=True)


def test_empty_leaderboard_is_public_and_read_only():
    client = APIClient()
    response = client.get(URL, {'game': 'battleship'})
    assert response.status_code == 200
    assert response.data == {'count': 0, 'next': None, 'previous': None, 'results': []}
    assert GameFund.objects.count() == GameRewardDecision.objects.count() == 0
    assert client.post(URL, {'game': 'battleship'}).status_code == 405


@pytest.mark.parametrize('query', [{}, {'game': ''}, {'game': 'chess'}, {'game': 'connect-five'}])
def test_requires_a_supported_game(query):
    response = APIClient().get(URL, query)
    assert response.status_code == 400
    assert 'game' in response.data


@pytest.mark.parametrize('game', GAMES)
def test_each_game_only_counts_its_paid_rewards(bucky_tnb_wallet, dmitry_tnb_wallet, game):
    contribute(user=bucky_tnb_wallet.owner, amount=200, request_id=uuid4())
    for reward_game in GAMES:
        pay(dmitry_tnb_wallet, game=reward_game)
    pay(dmitry_tnb_wallet, game=game, match_id=2)
    # Retrying settlement must never add another win or duplicate the amount.
    pay(dmitry_tnb_wallet, game=game, match_id=2)
    response = APIClient().get(URL, {'game': game})
    assert response.status_code == 200
    assert response.data['count'] == 1
    assert response.data['results'] == [
        {
            'rank': 1,
            'user': {'id': dmitry_tnb_wallet.owner_id, 'username': 'dmitry', 'avatar': None},
            'total_earned': 20,
            'rewarded_wins': 2,
        }
    ]


def test_guests_unfunded_and_ineligible_results_never_enter_leaderboard(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=20, request_id=uuid4())
    guest = settle_computer_reward(game='battleship', match_id=1, user_id=None, won=True)
    assert guest['status'] == 'guest'
    settle_computer_reward(game='battleship', match_id=2, user_id=bucky_tnb_wallet.owner_id, won=False)
    pay(dmitry_tnb_wallet, match_id=3)
    pay(dmitry_tnb_wallet, match_id=4)
    assert pay(bucky_tnb_wallet, match_id=5)['status'] == 'fund_empty'
    assert pay(dmitry_tnb_wallet, match_id=6)['status'] == 'fund_empty'
    before = list(GameRewardDecision.objects.values())
    response = APIClient().get(URL, {'game': 'battleship'})
    assert response.data['count'] == 1
    assert response.data['results'][0]['total_earned'] == 20
    assert response.data['results'][0]['rewarded_wins'] == 2
    assert list(GameRewardDecision.objects.values()) == before
    assert GameFund.objects.get().balance == 0


def test_totals_use_recorded_payouts_not_current_wallet_balance_or_reward_rate(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=100, request_id=uuid4())
    pay(dmitry_tnb_wallet)
    # A historic payout may use a different reward rate.
    GameRewardDecision.objects.filter(game='battleship').update(amount=7)
    dmitry_tnb_wallet.change_balance(-1000, should_stream=False)
    result = APIClient().get(URL, {'game': 'battleship'}).data['results'][0]
    assert result['total_earned'] == 7
    assert result['rewarded_wins'] == 1


def test_ties_have_shared_global_ranks_and_stable_paginated_order(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=100, request_id=uuid4())
    pay(bucky_tnb_wallet, match_id=1)
    pay(bucky_tnb_wallet, match_id=2)
    pay(dmitry_tnb_wallet, match_id=3)
    pay(dmitry_tnb_wallet, match_id=4)
    third_user = baker.make('users.User', username='alice')
    settle_computer_reward(game='battleship', match_id=5, user_id=third_user.id, won=True)
    client = APIClient()
    results = []
    for page in (1, 2, 3):
        response = client.get(URL, {'game': 'battleship', 'page_size': 1, 'page': page, 'ordering': 'total_earned'})
        assert response.status_code == 200
        assert response.data['count'] == 3
        results.extend(response.data['results'])
    assert [entry['rank'] for entry in results] == [1, 1, 3]
    assert [entry['user']['username'] for entry in results] == ['bucky', 'dmitry', 'alice']
    assert [entry['total_earned'] for entry in results] == [20, 20, 10]


@pytest.mark.parametrize('authenticated', [False, True])
def test_page_size_is_bounded_and_profiles_do_not_add_queries(bucky_tnb_wallet, authenticated):
    fund = GameFund.objects.create()
    users = baker.make('users.User', _quantity=101)
    wallets = Wallet.objects.bulk_create([Wallet(owner=user, currency=bucky_tnb_wallet.currency) for user in users])
    GameRewardDecision.objects.bulk_create(
        [
            GameRewardDecision(
                fund=fund, user=wallet.owner, wallet=wallet, game='hex', match_id=index + 1, status='paid', amount=10
            )
            for index, wallet in enumerate(wallets)
        ]
    )
    client = APIClient()
    if authenticated:
        client.force_authenticate(bucky_tnb_wallet.owner)
    with CaptureQueriesContext(connection) as queries:
        response = client.get(URL, {'game': 'hex', 'page_size': 10000})
    assert response.status_code == 200
    assert response.data['count'] == 101
    assert len(response.data['results']) == 100
    assert response.data['next'] is not None
    assert sum(query['sql'].startswith('SELECT') for query in queries) == 2
    assert set(response.data['results'][0]['user']) == {'id', 'username', 'avatar'}


def test_leaderboard_reflects_new_settlements_without_a_backfill(bucky_tnb_wallet, dmitry_tnb_wallet):
    contribute(user=bucky_tnb_wallet.owner, amount=30, request_id=uuid4())
    client = APIClient()
    pay(dmitry_tnb_wallet)
    assert client.get(URL, {'game': 'battleship'}).data['results'][0]['total_earned'] == 10
    pay(dmitry_tnb_wallet, match_id=2)
    assert client.get(URL, {'game': 'battleship'}).data['results'][0]['total_earned'] == 20
