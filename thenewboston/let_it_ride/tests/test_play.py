"""A Let It Ride hand through the casino API: the deal, both decisions, timeouts and the money."""

from datetime import timedelta
from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.casino.models import CasinoBet, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from thenewboston.casino.services import CasinoError, create_commitment, move_funds, place_bet, reconcile_fund
from thenewboston.casino.tasks import reconcile_casino
from thenewboston.let_it_ride import engine
from thenewboston.let_it_ride.services import act, expire_hand
from thenewboston.let_it_ride.tasks import expire_let_it_ride_hands
from thenewboston.wallets.models import Wallet

pytestmark = pytest.mark.django_db

# Three tens after the last card; a pair of tens from the start.
MADE = (['TC', 'TD', '2H'], ['3S', 'TH'])
# Nothing until the last card, which pairs the ace.
LATE = (['AS', '7D', '2H'], ['9C', 'AH'])
# Nothing at all.
BUST = (['AS', '7D', '2H'], ['9C', '4H'])


@pytest.fixture(autouse=True)
def configs():
    for game, version in (('slots', 2), ('roulette', 1), ('let_it_ride', 1)):
        CasinoGameConfig.objects.update_or_create(game=game, defaults={'enabled': True, 'rules_version': version})
    CasinoGameConfig.objects.filter(game='let_it_ride').update(min_bet=3)


@pytest.fixture
def funded(bucky_tnb_wallet):
    wallet = bucky_tnb_wallet
    wallet.owner.is_staff = True
    wallet.owner.save(update_fields=['is_staff'])
    wallet.balance = 200000
    wallet.save(should_adjust_timestamps=False)
    move_funds(user=wallet.owner, amount=100000, request_id=uuid4(), kind='deposit')
    return wallet.owner


@pytest.fixture
def client(funded):
    api_client = APIClient()
    api_client.force_authenticate(funded)
    return api_client


@pytest.fixture
def stack(monkeypatch):
    """Deal chosen cards. Acceptance and every later verification use the same deal, as real seeds do."""

    def use(cards, community):
        monkeypatch.setattr(engine, 'deal', lambda random: (list(cards), list(community)))

    return use


def wager(user, **changes):
    commitment = create_commitment(user=user)
    return {
        'request_id': str(uuid4()),
        'commitment_id': str(commitment.id),
        'client_seed': 'test-client',
        'game': 'let_it_ride',
        'amount': 9,
        'rules_version': 1,
        **changes,
    }


def deal(client, user, **changes):
    response = client.post('/api/casino/bets', wager(user, **changes), format='json')
    assert response.status_code == 201, response.data
    return response.data


def decide(client, receipt, action, revision, action_id=None):
    return client.post(
        f'/api/casino/bets/{receipt["request_id"]}/actions',
        {'action_id': action_id or str(uuid4()), 'action': action, 'expected_revision': revision},
        format='json',
    )


def balance(user):
    return Wallet.objects.get(owner=user, currency__ticker='TNB').balance


def overdue(receipt):
    CasinoBet.objects.filter(pk=receipt['id']).update(
        created_date=timezone.now() - timedelta(seconds=engine.TIMEOUT_SECONDS + 1)
    )


def test_the_deal_takes_three_bets_and_shows_only_the_player_cards(client, funded, stack):
    stack(*MADE)
    receipt = deal(client, funded)
    assert receipt['status'] == 'open'
    assert (receipt['amount'], receipt['total_stake'], receipt['payout'], receipt['profit']) == (9, 9, 0, None)
    assert receipt['result']['cards'] == ['TC', 'TD', '2H']
    assert receipt['result']['community'] == [None, None]
    assert receipt['result']['available_actions'] == ['ride', 'pull']
    assert receipt['fairness']['server_seed'] is None
    assert receipt['wallet_balance'] == balance(funded) == 100000 - 9
    # All three bets and the largest possible win are set aside until the hand ends.
    fund = CasinoFund.objects.get(pk=1)
    assert (fund.balance, fund.reserved) == (100009, 9 * 101)
    assert receipt['fund']['reserved'] == 909
    assert reconcile_fund()['open_bets'] == 1
    assert 'TH' not in str(receipt) and '3S' not in str(receipt)
    assert client.get('/api/casino/bets/active').data['id'] == receipt['id']
    assert client.get(f'/api/casino/bets/{receipt["request_id"]}').data['result']['community'] == [None, None]
    assert client.get('/api/casino/bets').data[0]['result']['community'] == [None, None]


def test_letting_every_bet_ride_pays_all_three(client, funded, stack):
    stack(*MADE)
    receipt = deal(client, funded)
    first = decide(client, receipt, 'ride', 0)
    assert first.status_code == 200
    assert first.data['status'] == 'open'
    assert first.data['result']['community'] == ['3S', None]
    assert (first.data['result']['phase'], first.data['result']['revision']) == ('second', 1)
    assert first.data['fairness']['server_seed'] is None
    assert balance(funded) == 100000 - 9
    last = decide(client, receipt, 'ride', 1)
    assert last.status_code == 200
    result = last.data['result']
    assert last.data['status'] == 'settled' and last.data['settlement_reason'] == 'completed'
    assert result['community'] == ['3S', 'TH']
    assert (result['hand'], result['odds'], result['riding'], result['decisions']) == (
        'three_of_a_kind',
        3,
        3,
        ['ride', 'ride'],
    )
    # Three bets of 3 TNB at 3 to 1: 9 TNB each in winnings plus the bets themselves.
    assert (last.data['payout'], last.data['profit']) == (36, 27)
    assert last.data['wallet_balance'] == balance(funded) == 100000 + 27
    assert last.data['fairness']['server_seed']
    fund = CasinoFund.objects.get(pk=1)
    assert (fund.balance, fund.reserved) == (100000 - 27, 0)
    assert [entry.kind for entry in CasinoLedgerEntry.objects.filter(bet_id=receipt['id']).order_by('id')] == [
        'stake',
        'payout',
    ]
    assert reconcile_fund()['open_bets'] == 0
    assert client.get('/api/casino/bets/active').json() is None


@pytest.mark.parametrize(
    'cards,decisions,payout,riding,hand',
    [
        # A pulled bet comes straight back; the bets left out are paid on the final hand.
        (MADE, ['pull', 'ride'], 3 + 2 * 12, 2, 'three_of_a_kind'),
        (MADE, ['pull', 'pull'], 6 + 12, 1, 'three_of_a_kind'),
        (LATE, ['pull', 'pull'], 6 + 6, 1, 'tens_or_better'),
        (LATE, ['ride', 'pull'], 3 + 2 * 6, 2, 'tens_or_better'),
        # A losing hand keeps every bet still riding.
        (BUST, ['pull', 'pull'], 6, 1, engine.NO_WIN),
        (BUST, ['ride', 'ride'], 0, 3, engine.NO_WIN),
    ],
)
def test_pulled_bets_come_back_and_riding_bets_follow_the_hand(
    client, funded, stack, cards, decisions, payout, riding, hand
):
    stack(*cards)
    receipt = deal(client, funded)
    for revision, action in enumerate(decisions):
        response = decide(client, receipt, action, revision)
        assert response.status_code == 200
    assert response.data['status'] == 'settled'
    assert (response.data['payout'], response.data['profit']) == (payout, payout - 9)
    assert (response.data['result']['riding'], response.data['result']['hand']) == (riding, hand)
    assert balance(funded) == 100000 - 9 + payout
    assert reconcile_fund() == {
        'balance': 100000 + 9 - payout,
        'reserved': 0,
        'ledger_balance': 100000 + 9 - payout,
        'expected_reserved': 0,
        'open_bets': 0,
    }


def test_a_royal_flush_with_every_bet_riding_is_fully_covered(client, funded, stack):
    stack(['TS', 'JS', 'QS'], ['KS', 'AS'])
    receipt = deal(client, funded)
    decide(client, receipt, 'ride', 0)
    last = decide(client, receipt, 'ride', 1)
    assert (last.data['result']['hand'], last.data['payout']) == ('royal_flush', 9 * 101)
    assert CasinoFund.objects.get(pk=1).balance == 100009 - 909
    assert reconcile_fund()['reserved'] == 0


@pytest.mark.parametrize('amount', [4, 10, 100])
def test_a_wager_that_is_not_three_equal_bets_is_rejected_before_charging(client, funded, amount):
    response = client.post('/api/casino/bets', wager(funded, amount=amount), format='json')
    assert response.status_code == 400
    assert 'multiple of 3' in response.data['detail']
    assert not CasinoBet.objects.exists()
    assert balance(funded) == 100000


def test_limits_follow_the_fund_and_the_minimum(client, funded):
    game = {item['id']: item for item in client.get('/api/casino').data['games']}['let_it_ride']
    assert (game['min_bet'], game['max_bet'], game['available'], game['bet_increment']) == (3, 9, True, 3)
    assert game['name'] == 'Let It Ride'
    over = client.post('/api/casino/bets', wager(funded, amount=12), format='json')
    assert over.status_code == 400 and over.data['code'] == 'bet_limit'
    CasinoGameConfig.objects.filter(game='let_it_ride').update(min_bet=6)
    under = client.post('/api/casino/bets', wager(funded, amount=3), format='json')
    assert under.status_code == 400 and under.data['code'] == 'bet_limit'
    assert not CasinoBet.objects.exists()


def test_a_decision_is_applied_once_however_often_it_is_sent(client, funded, stack):
    stack(*MADE)
    receipt = deal(client, funded)
    action_id = str(uuid4())
    first = decide(client, receipt, 'pull', 0, action_id)
    again = decide(client, receipt, 'pull', 0, action_id)
    assert first.status_code == again.status_code == 200
    assert again.data['result'] == first.data['result']
    assert again.data['result']['decisions'] == ['pull']
    # The same ID with a different decision or revision is a conflict, never a second action.
    assert decide(client, receipt, 'ride', 0, action_id).status_code == 409
    assert decide(client, receipt, 'pull', 1, action_id).data['code'] == 'request_conflict'
    # A new action against a revision that has passed is refused too.
    stale = decide(client, receipt, 'ride', 0)
    assert stale.status_code == 409 and stale.data['code'] == 'revision_conflict'
    last_id = str(uuid4())
    last = decide(client, receipt, 'ride', 1, last_id)
    assert last.data['status'] == 'settled'
    # Retrying the final action returns the same settled receipt and pays nothing more.
    replay = decide(client, receipt, 'ride', 1, last_id)
    assert replay.status_code == 200 and replay.data['payout'] == last.data['payout'] == 3 + 2 * 12
    assert balance(funded) == 100000 - 9 + 27
    late = decide(client, receipt, 'ride', 1)
    assert late.status_code == 409 and late.data['code'] == 'hand_settled'
    assert CasinoLedgerEntry.objects.filter(bet_id=receipt['id'], kind='payout').count() == 1


@pytest.mark.parametrize(
    'body',
    [
        {'action': 'ride', 'expected_revision': 0},
        {'action_id': 'not-a-uuid', 'action': 'ride', 'expected_revision': 0},
        {'action_id': str(uuid4()), 'action': 'fold', 'expected_revision': 0},
        {'action_id': str(uuid4()), 'action': 'ride', 'expected_revision': 2},
        {'action_id': str(uuid4()), 'action': 'ride', 'expected_revision': '0'},
        {'action_id': str(uuid4()), 'action': 'ride', 'expected_revision': -1},
        {'action_id': str(uuid4()), 'action': 'ride'},
    ],
)
def test_invalid_actions_leave_the_hand_untouched(client, funded, stack, body):
    stack(*MADE)
    receipt = deal(client, funded)
    response = client.post(f'/api/casino/bets/{receipt["request_id"]}/actions', body, format='json')
    assert response.status_code == 400
    assert CasinoBet.objects.get(pk=receipt['id']).result['decisions'] == []


def test_a_hand_belongs_to_its_player(client, funded, stack, dmitry):
    stack(*MADE)
    receipt = deal(client, funded)
    other = APIClient()
    other.force_authenticate(dmitry)
    assert decide(other, receipt, 'ride', 0).status_code == 404
    assert other.get('/api/casino/bets/active').json() is None
    assert APIClient().get('/api/casino/bets/active').status_code == 401
    assert decide(APIClient(), receipt, 'ride', 0).status_code == 401
    with pytest.raises(CasinoError) as error:
        act(user=dmitry, request_id=receipt['request_id'], action_id=uuid4(), action='ride', expected_revision=0)
    assert error.value.status == 404
    assert decide(client, {'request_id': str(uuid4())}, 'ride', 0).status_code == 404
    assert CasinoBet.objects.get(pk=receipt['id']).result['decisions'] == []


def test_an_instant_game_has_no_actions(client, funded):
    payload = wager(funded, game='slots', amount=5, rules_version=2)
    receipt = client.post('/api/casino/bets', payload, format='json').data
    assert receipt['status'] == 'settled' and receipt['settlement_reason'] == 'completed'
    response = decide(client, receipt, 'ride', 0)
    assert response.status_code == 400
    assert response.data['detail'] == 'This game does not support interactive play.'


def test_an_open_hand_blocks_other_wagers_until_it_ends(client, funded, stack):
    stack(*MADE)
    receipt = deal(client, funded)
    for game, version in (('slots', 2), ('let_it_ride', 1)):
        blocked = client.post(
            '/api/casino/bets', wager(funded, game=game, amount=3, rules_version=version), format='json'
        )
        assert blocked.status_code == 409 and blocked.data['code'] == 'game_in_progress'
    # Sending the same deal again returns the same open hand instead of charging twice.
    payload = wager(funded)
    payload.update(request_id=receipt['request_id'], commitment_id=receipt['fairness']['commitment_id'])
    same = client.post('/api/casino/bets', payload, format='json')
    assert same.status_code == 201 and same.data['id'] == receipt['id']
    assert balance(funded) == 100000 - 9
    decide(client, receipt, 'pull', 0)
    decide(client, receipt, 'pull', 1)
    assert (
        client.post('/api/casino/bets', wager(funded, game='slots', amount=3, rules_version=2), format='json').data[
            'status'
        ]
        == 'settled'
    )


def test_an_abandoned_hand_times_out_and_pulls_back_what_could_lose(client, funded, stack):
    stack(*LATE)
    receipt = deal(client, funded)
    assert expire_let_it_ride_hands() == {'settled': 0}
    assert expire_hand(bet_id=receipt['id']).status == 'open'
    overdue(receipt)
    assert expire_let_it_ride_hands() == {'settled': 1}
    bet = CasinoBet.objects.get(pk=receipt['id'])
    assert (bet.status, bet.settlement_reason) == ('settled', 'timeout')
    assert bet.result['decisions'] == ['pull', 'pull'] and bet.result['action_ids'] == [None, None]
    # Both optional bets come back; the third always plays and found the pair of aces.
    assert bet.payout == 6 + 6
    assert balance(funded) == 100000 + 3
    assert reconcile_fund()['reserved'] == 0
    assert expire_let_it_ride_hands() == {'settled': 0}
    settled = client.get(f'/api/casino/bets/{receipt["request_id"]}').data
    assert settled['settlement_reason'] == 'timeout' and settled['result']['community'] == ['9C', 'AH']


def test_a_timed_out_hand_that_already_pays_keeps_riding(client, funded, stack):
    stack(*MADE)
    receipt = deal(client, funded)
    decide(client, receipt, 'pull', 0)
    overdue(receipt)
    assert expire_let_it_ride_hands() == {'settled': 1}
    bet = CasinoBet.objects.get(pk=receipt['id'])
    # The player's own decision stands; the unattended bet rides because a pair of tens cannot lose.
    assert bet.result['decisions'] == ['pull', 'ride']
    assert (bet.settlement_reason, bet.payout) == ('timeout', 3 + 2 * 12)


def test_an_overdue_hand_cannot_be_played_even_before_the_sweep_runs(client, funded, stack):
    stack(*BUST)
    receipt = deal(client, funded)
    overdue(receipt)
    response = decide(client, receipt, 'ride', 0)
    assert response.status_code == 200
    assert (response.data['status'], response.data['settlement_reason']) == ('settled', 'timeout')
    assert response.data['result']['decisions'] == ['pull', 'pull']
    assert response.data['payout'] == 6
    assert balance(funded) == 100000 - 3


def test_shared_recovery_and_verification_leave_an_open_hand_alone(client, funded, stack):
    stack(*MADE)
    receipt = deal(client, funded)
    CasinoBet.objects.filter(pk=receipt['id']).update(created_date=timezone.now() - timedelta(minutes=2))
    assert reconcile_casino()['open_bets'] == 1
    output = StringIO()
    call_command('verify_casino', stdout=output)
    assert 'Casino verified' in output.getvalue()
    assert CasinoBet.objects.get(pk=receipt['id']).status == 'open'
    # Closing the game or the casino stops new deals, never a hand already in play.
    CasinoGameConfig.objects.filter(game='let_it_ride').update(enabled=False)
    CasinoFund.objects.filter(pk=1).update(enabled=False)
    decide(client, receipt, 'ride', 0)
    assert decide(client, receipt, 'ride', 1).data['payout'] == 36


@pytest.mark.parametrize(
    'tamper',
    [
        lambda bet: bet.result.update(community=['3S', 'AS']),
        lambda bet: bet.result.update(cards=['AC', 'AD', 'AH']),
        lambda bet: bet.result.update(decisions=['ride'], revision=0),
        lambda bet: bet.result.update(riding=1),
        lambda bet: setattr(bet, 'house_exposure', 0),
        lambda bet: bet.result.pop('action_ids'),
    ],
)
def test_a_hand_that_does_not_match_its_commitment_is_never_paid(client, funded, tamper):
    receipt = deal(client, funded)
    bet = CasinoBet.objects.get(pk=receipt['id'])
    tamper(bet)
    CasinoBet.objects.filter(pk=bet.pk).update(result=bet.result, house_exposure=bet.house_exposure)
    overdue(receipt)
    with pytest.raises(RuntimeError, match='reservation retained'):
        act(
            user=funded,
            request_id=receipt['request_id'],
            action_id=uuid4(),
            action='ride',
            expected_revision=0,
        )
    with pytest.raises(RuntimeError, match='reservation retained'):
        expire_hand(bet_id=bet.pk)
    # The sweep reports the failure and keeps going; the bet stays open and its money stays where it was.
    assert expire_let_it_ride_hands() == {'settled': 0}
    assert CasinoBet.objects.get(pk=bet.pk).status == 'open'
    assert balance(funded) == 100000 - 9
    assert CasinoFund.objects.get(pk=1).balance == 100009


def test_real_seeds_deal_a_hand_that_the_revealed_seed_reproduces(client, funded):
    from thenewboston.casino.fairness import FairRandom, seed_hash

    receipt = deal(client, funded)
    decide(client, receipt, 'pull', 0)
    settled = decide(client, receipt, 'pull', 1).data
    fairness = settled['fairness']
    assert seed_hash(fairness['server_seed']) == fairness['server_seed_hash'] == receipt['fairness']['server_seed_hash']
    random = FairRandom(
        server_seed=fairness['server_seed'],
        client_seed=fairness['client_seed'],
        commitment_id=fairness['commitment_id'],
        game='let_it_ride',
        rules_version=1,
    )
    cards, community = engine.deal(random)
    assert (cards, community) == (settled['result']['cards'], settled['result']['community'])
    assert cards == receipt['result']['cards']
    state = engine.replay(cards, community, settled['result']['decisions'], [None, None])
    assert engine.payout(settled['amount'], state) == settled['payout']
    assert state['hand'] == settled['result']['hand']


def test_place_bet_service_keeps_the_stake_reserved_for_an_open_hand(funded, stack):
    stack(*MADE)
    payload = wager(funded)
    bet, fund, wallet = place_bet(user=funded, **payload)
    assert (bet.status, bet.total_stake, bet.house_exposure) == ('open', 9, 900)
    assert (fund.reserved, wallet.balance) == (909, 100000 - 9)
    assert bet.result['community'] == ['3S', 'TH']
