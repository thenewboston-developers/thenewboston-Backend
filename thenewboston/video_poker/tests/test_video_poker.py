from copy import deepcopy
from datetime import timedelta
from importlib import import_module
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone
from rest_framework.test import APIClient

from thenewboston.casino.fairness import decrypt_seed
from thenewboston.casino.models import MAX_SAFE_INTEGER, CasinoBet, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from thenewboston.casino.services import (
    CasinoError,
    bet_receipt,
    create_commitment,
    move_funds,
    place_bet,
    reconcile_fund,
)
from thenewboston.casino.tasks import reconcile_casino
from thenewboston.casino.tests.test_financial_safety import accepted, race
from thenewboston.video_poker import engine
from thenewboston.video_poker.models import VideoPokerDraw
from thenewboston.video_poker.services import act, expire_hand
from thenewboston.video_poker.tasks import expire_video_poker_hands
from thenewboston.wallets.models import Wallet
from thenewboston.wallets.serializers.wallet import WalletReadSerializer

pytestmark = pytest.mark.django_db(transaction=True)

# Dealt three kings. Holding them draws a pair of twos for a full house; discarding everything draws nothing.
DECK = ['KS', 'KH', '4D', '7C', 'KD', '2S', '2H', '9C', '5D', '8H', 'AC']
ROYAL = ['10S', 'JS', 'QS', 'KS', '3D', 'AS', '2H', '9C', '5D', '8H']
HOLD_KINGS = 'draw:11001'


@pytest.fixture
def treasury(bucky_tnb_wallet, monkeypatch):
    monkeypatch.setattr(Wallet, 'stream', lambda self: None)
    owner = bucky_tnb_wallet.owner
    owner.is_staff = True
    owner.save(update_fields=['is_staff'])
    Wallet.objects.filter(pk=bucky_tnb_wallet.pk).update(balance=200_000)
    CasinoGameConfig.objects.update_or_create(
        game='video_poker', defaults={'enabled': True, 'rules_version': 1, 'min_bet': 1}
    )
    move_funds(user=owner, amount=100_000, request_id=uuid4(), kind='deposit')
    monkeypatch.setattr(engine, 'shuffled_deck', lambda random: list(DECK))
    return owner


def request(user, **changes):
    commitment = create_commitment(user=user)
    return {
        'user': user,
        'request_id': uuid4(),
        'commitment_id': commitment.pk,
        'client_seed': 'video-poker-tests',
        'game': 'video_poker',
        'amount': 4,
        'rules_version': 1,
        **changes,
    }


def action(user, bet, **changes):
    return {
        'user': user,
        'request_id': bet.request_id,
        'action_id': uuid4(),
        'action': HOLD_KINGS,
        'expected_revision': bet.result['revision'],
        **changes,
    }


def expire(bet):
    CasinoBet.objects.filter(pk=bet.pk).update(created_date=timezone.now() - timedelta(minutes=16))
    bet.refresh_from_db()


def test_migration_enables_the_game_without_funding_it_and_rollback_only_closes_it():
    migration = import_module('thenewboston.video_poker.migrations.0002_initial_configuration')
    CasinoGameConfig.objects.filter(game='video_poker').delete()
    migration.configure_video_poker(apps, None)
    config = CasinoGameConfig.objects.get(game='video_poker')
    assert (config.enabled, config.rules_version, config.min_bet) == (True, 1, 1)
    CasinoGameConfig.objects.filter(game='video_poker').update(min_bet=2)
    migration.configure_video_poker(apps, None)
    assert CasinoGameConfig.objects.get(game='video_poker').min_bet == 2
    migration.disable_video_poker(apps, None)
    config.refresh_from_db()
    assert (config.enabled, config.min_bet) == (False, 2)
    assert not CasinoLedgerEntry.objects.exists() and not CasinoFund.objects.exclude(balance=0).exists()


def test_open_hand_is_recoverable_and_never_leaks_undealt_cards_or_seed(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    payload = request(user)
    bet, _, wallet = place_bet(**payload)
    assert bet.status == 'open' and wallet.balance == 996
    assert (bet.house_exposure, bet.total_stake) == (996, 4)
    assert reconcile_fund()['reserved'] == 1000
    client = APIClient()
    client.force_authenticate(user)
    responses = [
        client.get(f'/api/casino/bets/{bet.request_id}').data,
        client.get('/api/casino/bets/active').data,
        client.get('/api/casino/bets').data[0],
        bet_receipt(place_bet(**payload)[0]),
    ]
    for receipt in responses:
        assert receipt['status'] == 'open' and receipt['payout'] == 0 and receipt['profit'] is None
        assert receipt['fairness']['server_seed'] is None
        assert receipt['result']['dealt'] == receipt['result']['hand'] == DECK[:5]
        assert receipt['result']['category'] == 'three_of_a_kind'
        assert receipt['result']['held'] is None
        assert receipt['result']['available_actions'] == ['draw']
        assert receipt['result']['expires_at']
        assert not {'deck', 'actions', 'multiplier'} & receipt['result'].keys()
        assert not any(card in str(receipt['result']) for card in DECK[5:])
    assert not any(card in str(bet.result) for card in DECK[5:])
    client.force_authenticate(treasury)
    assert client.get('/api/casino/bets/active').content == b'null'
    assert client.get(f'/api/casino/bets/{bet.request_id}').status_code == 404
    with pytest.raises(CasinoError) as error:
        place_bet(**request(user, amount=1))
    assert error.value.data['code'] == 'game_in_progress'
    # The shared instant-game recovery leaves an open hand alone.
    CasinoBet.objects.filter(pk=bet.pk).update(created_date=timezone.now() - timedelta(minutes=2))
    assert reconcile_casino()['open_bets'] == 1


def test_open_and_settled_receipts_include_the_matching_wallet_revision(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    client = APIClient()
    client.force_authenticate(user)
    payload = request(user)
    del payload['user']
    placed = client.post('/api/casino/bets', payload, format='json')
    assert placed.status_code == 201 and placed.json()['status'] == 'open'
    request_id = placed.json()['request_id']
    open_wallet = WalletReadSerializer(Wallet.objects.get(pk=dmitry_tnb_wallet.pk)).data
    open_receipts = [
        placed.json(),
        client.get(f'/api/casino/bets/{request_id}').json(),
        client.get('/api/casino/bets/active').json(),
        client.get('/api/casino/bets').json()[0],
    ]
    for receipt in open_receipts:
        assert receipt['wallet_balance'] == open_wallet['balance'] == 996
        assert receipt['wallet_modified_date'] == open_wallet['modified_date']

    play = {'action': HOLD_KINGS, 'action_id': str(uuid4()), 'expected_revision': 0}
    settled = client.post(f'/api/casino/bets/{request_id}/actions', play, format='json')
    assert settled.status_code == 200 and settled.json()['status'] == 'settled'
    settled_wallet = WalletReadSerializer(Wallet.objects.get(pk=dmitry_tnb_wallet.pk)).data
    assert settled_wallet['modified_date'] != open_wallet['modified_date']
    replay = client.post(f'/api/casino/bets/{request_id}/actions', play, format='json')
    assert replay.status_code == 200
    for receipt in (settled.json(), replay.json()):
        assert receipt['wallet_balance'] == settled_wallet['balance'] == 1032
        assert receipt['wallet_modified_date'] == settled_wallet['modified_date']


def test_catalog_reports_the_pay_table_limits_and_perfect_play_return(treasury):
    entry = next(game for game in APIClient().get('/api/casino').data['games'] if game['id'] == 'video_poker')
    assert entry['name'] == 'Video Poker' and entry['available']
    assert (entry['min_bet'], entry['max_bet'], entry['max_multiplier']) == (1, 4, 250)
    assert entry['house_edge'] == pytest.approx(0.01626543)
    assert entry['optimal_return'] == pytest.approx(0.98373457)
    assert entry['pay_table'][0] == {'hand': 'royal_flush', 'name': 'Royal Flush', 'multiplier': 250}
    assert entry['pay_table'][-1] == {'hand': 'jacks_or_better', 'name': 'Jacks or Better', 'multiplier': 1}
    assert entry['timeout_seconds'] == 900 and entry['decks'] == 1


@pytest.mark.parametrize('amount', [5, 1000])
def test_wagers_above_the_covered_limit_are_rejected_before_any_transfer(treasury, dmitry_tnb_wallet, amount):
    with pytest.raises(CasinoError) as error:
        place_bet(**request(dmitry_tnb_wallet.owner, amount=amount))
    assert error.value.data['code'] == 'bet_limit' and error.value.data['max_bet'] == 4
    with pytest.raises(CasinoError, match='does not accept a selection'):
        place_bet(**request(dmitry_tnb_wallet.owner, selection={'hold': [0, 1]}))
    assert not CasinoBet.objects.exists()
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1000
    assert reconcile_fund()['balance'] == 100_000


def test_draw_replaces_discards_and_pays_exactly_once_even_after_closure(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    payload = request(user)
    bet, _, _ = place_bet(**payload)
    CasinoFund.objects.update(enabled=False)
    CasinoGameConfig.objects.update(enabled=False)
    play = action(user, bet)
    bet, fund, wallet = act(**play)
    assert (bet.status, bet.total_stake, bet.payout, wallet.balance) == ('settled', 4, 36, 1032)
    assert bet.settlement_reason == 'completed'
    assert bet.result['hand'] == ['KS', 'KH', '2S', '2H', 'KD']
    assert bet.result['held'] == [True, True, False, False, True]
    assert (bet.result['category'], bet.result['multiplier']) == ('full_house', 9)
    assert fund.reserved == 0
    assert act(**play)[0].pk == bet.pk
    assert place_bet(**payload)[0].payout == 36
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='stake').count() == 1
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert VideoPokerDraw.objects.get(bet=bet).action == HOLD_KINGS
    assert reconcile_fund()['balance'] == 99_968
    receipt = bet_receipt(bet)
    assert receipt['profit'] == 32
    assert receipt['fairness']['server_seed'] == decrypt_seed(bet.commitment.encrypted_server_seed)
    assert receipt['result']['actions'] == [HOLD_KINGS]
    assert receipt['result']['dealt'] == DECK[:5]
    assert receipt['result']['available_actions'] == [] and receipt['result']['expires_at'] is None


@pytest.mark.parametrize(
    'holds,hand,category,payout',
    [
        ('draw:11111', ['KS', 'KH', '4D', '7C', 'KD'], 'three_of_a_kind', 12),
        ('draw:00000', ['2S', '2H', '9C', '5D', '8H'], 'nothing', 0),
        ('draw:11000', ['KS', 'KH', '2S', '2H', '9C'], 'two_pair', 8),
        ('draw:10000', ['KS', '2S', '2H', '9C', '5D'], 'nothing', 0),
    ],
)
def test_every_hold_pattern_settles_at_its_pay_table_multiplier(
    treasury, dmitry_tnb_wallet, holds, hand, category, payout
):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    bet, _, wallet = act(**action(user, bet, action=holds))
    assert (bet.result['hand'], bet.result['category'], bet.payout) == (hand, category, payout)
    assert wallet.balance == 996 + payout
    assert CasinoLedgerEntry.objects.get(bet=bet, kind='payout').amount == payout
    assert reconcile_fund() == {
        'balance': 100_004 - payout,
        'reserved': 0,
        'ledger_balance': 100_004 - payout,
        'expected_reserved': 0,
        'open_bets': 0,
    }


def test_royal_flush_remains_covered_after_admin_withdraws_every_free_coin(treasury, dmitry_tnb_wallet, monkeypatch):
    monkeypatch.setattr(engine, 'shuffled_deck', lambda random: list(ROYAL))
    user = dmitry_tnb_wallet.owner
    bet, fund, _ = place_bet(**request(user))
    move_funds(user=treasury, amount=fund.available, request_id=uuid4(), kind='withdrawal')
    assert reconcile_fund()['balance'] == reconcile_fund()['reserved'] == 1000
    with pytest.raises(CasinoError) as error:
        move_funds(user=treasury, amount=1, request_id=uuid4(), kind='withdrawal')
    assert error.value.data['code'] == 'funds_reserved'
    bet, _, wallet = act(**action(user, bet, action='draw:11110'))
    assert (bet.result['category'], bet.payout) == ('royal_flush', 1000)
    assert wallet.balance == 1996
    assert reconcile_fund()['balance'] == reconcile_fund()['reserved'] == 0


def test_invalid_actions_revisions_conflicts_and_other_users_never_settle(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    for changes in (
        {'action': 'draw'},
        {'action': 'hit'},
        {'action': 'draw:1100'},
        {'action': 'draw:11002'},
        {'action': None},
        {'expected_revision': True},
        {'expected_revision': 2},
        {'expected_revision': 1},
        {'user': treasury},
        {'request_id': uuid4()},
        {'action_id': 'not-a-uuid'},
    ):
        with pytest.raises(CasinoError):
            act(**{**action(user, bet), **changes})
    bet.refresh_from_db()
    assert bet.status == 'open' and bet.result['revision'] == 0
    assert not VideoPokerDraw.objects.exists()
    play = action(user, bet)
    bet, _, _ = act(**play)
    with pytest.raises(CasinoError) as error:
        act(**{**play, 'action': 'draw:11111'})
    assert error.value.data['code'] == 'request_conflict'
    with pytest.raises(CasinoError) as error:
        act(**action(user, bet, action='draw:00000'))
    assert error.value.data['code'] == 'hand_settled'
    assert bet.payout == 36
    assert CasinoLedgerEntry.objects.filter(bet=bet).count() == 2
    assert reconcile_fund()['reserved'] == 0


def test_action_api_validates_input_and_settles_the_hand(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    client = APIClient()
    url = f'/api/casino/bets/{bet.request_id}/actions'
    payload = {'action': HOLD_KINGS, 'action_id': str(uuid4()), 'expected_revision': 0}
    assert client.post(url, payload, format='json').status_code == 401
    client.force_authenticate(treasury)
    assert client.post(url, payload, format='json').status_code == 404
    client.force_authenticate(user)
    for changes in ({'expected_revision': False}, {'action': 'draw:hold'}, {'action': 'stand'}, {'action_id': 'x'}):
        response = client.post(url, {**payload, **changes}, format='json')
        assert response.status_code == 400, changes
    stale = client.post(url, {**payload, 'expected_revision': 1}, format='json')
    assert stale.status_code == 409 and stale.data['code'] == 'revision_conflict'
    result = client.post(url, payload, format='json')
    assert result.status_code == 200 and result.data['status'] == 'settled'
    assert result.data['payout'] == 36 and result.data['wallet_balance'] == 1032
    assert result.data['result']['hand'] == ['KS', 'KH', '2S', '2H', 'KD']
    assert result.data['fairness']['server_seed']
    assert client.post(url, payload, format='json').data == result.data
    assert client.get('/api/casino/bets/active').content == b'null'
    assert reconcile_fund()['reserved'] == 0


def test_timeout_holds_every_card_once_and_a_late_draw_cannot_change_it(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    expire(bet)
    bet, _, wallet = act(**action(user, bet, action='draw:00000'))
    assert bet.settlement_reason == 'timeout'
    assert bet.result['actions'] == ['draw:11111'] and bet.result['hand'] == DECK[:5]
    assert bet.payout == 12 and wallet.balance == 1008
    assert not VideoPokerDraw.objects.exists()
    assert expire_hand(bet_id=bet.pk).pk == bet.pk
    assert expire_video_poker_hands() == {'settled': 0}
    assert CasinoLedgerEntry.objects.filter(bet=bet).count() == 2
    assert reconcile_fund()['reserved'] == 0


def test_worker_only_expires_overdue_video_poker_hands(treasury, dmitry_tnb_wallet):
    bet, _, _ = place_bet(**request(dmitry_tnb_wallet.owner))
    assert expire_video_poker_hands() == {'settled': 0}
    assert expire_hand(bet_id=bet.pk).status == 'open'
    expire(bet)
    assert expire_video_poker_hands() == {'settled': 1}
    assert expire_video_poker_hands() == {'settled': 0}
    bet.refresh_from_db()
    assert (bet.settlement_reason, bet.payout) == ('timeout', 12)
    assert reconcile_fund()['reserved'] == 0


def test_corrupt_state_retains_reservation_and_is_never_rerolled(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    damaged = deepcopy(bet.result)
    damaged['dealt'][0] = damaged['hand'][0] = 'AS'
    CasinoBet.objects.filter(pk=bet.pk).update(result=damaged)
    with pytest.raises(RuntimeError, match='verification failed'):
        act(**action(user, bet))
    expire(bet)
    assert expire_video_poker_hands() == {'settled': 0}
    bet.refresh_from_db()
    assert bet.status == 'open' and bet.result == damaged
    assert reconcile_fund()['reserved'] == 1000
    assert not VideoPokerDraw.objects.exists()


def test_failed_payout_ledger_rolls_back_the_draw(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    original = deepcopy(bet.result)
    create = CasinoLedgerEntry.objects.create

    def fail_payout(**kwargs):
        if kwargs['kind'] == 'payout':
            raise RuntimeError('simulated payout ledger failure')
        return create(**kwargs)

    play = action(user, bet)
    with patch.object(CasinoLedgerEntry.objects, 'create', side_effect=fail_payout):
        with pytest.raises(RuntimeError, match='simulated'):
            act(**play)
    bet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert bet.result == original and bet.status == 'open'
    assert dmitry_tnb_wallet.balance == 996
    assert not VideoPokerDraw.objects.exists()
    assert reconcile_fund()['reserved'] == 1000
    assert act(**play)[0].payout == 36


def test_external_wallet_credit_cannot_selectively_block_only_winning_draws(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    Wallet.objects.filter(pk=dmitry_tnb_wallet.pk).update(balance=MAX_SAFE_INTEGER)
    with patch.object(engine, 'apply_action', side_effect=AssertionError('do not derive an outcome')) as derive:
        for choice in ('draw:11111', 'draw:00000', HOLD_KINGS):
            with pytest.raises(CasinoError) as error:
                act(**action(user, bet, action=choice))
            assert error.value.data['code'] == 'wallet_limit'
        expire(bet)
        with pytest.raises(RuntimeError, match='capacity'):
            expire_hand(bet_id=bet.pk)
        derive.assert_not_called()
    assert reconcile_fund()['reserved'] == 1000
    Wallet.objects.filter(pk=dmitry_tnb_wallet.pk).update(balance=996)
    assert expire_hand(bet_id=bet.pk).status == 'settled'


def test_concurrent_draw_retry_pays_once(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    play = action(user, bet)
    results = race(*[lambda: act(**play)[0].payout for _ in range(3)])
    assert results == [36, 36, 36]
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert VideoPokerDraw.objects.filter(bet=bet).count() == 1
    dmitry_tnb_wallet.refresh_from_db()
    assert dmitry_tnb_wallet.balance == 1032
    assert reconcile_fund()['reserved'] == 0


def test_two_different_draws_racing_settle_exactly_one(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    race(
        lambda: accepted(lambda: act(**action(user, bet, action=HOLD_KINGS))),
        lambda: accepted(lambda: act(**action(user, bet, action='draw:11111'))),
    )
    bet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert bet.status == 'settled' and bet.payout in (36, 12)
    assert dmitry_tnb_wallet.balance == 996 + bet.payout
    assert VideoPokerDraw.objects.get(bet=bet).action == bet.result['actions'][0]
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert reconcile_fund()['reserved'] == 0


def test_timeout_racing_with_player_draw_cannot_settle_twice(treasury, dmitry_tnb_wallet):
    user = dmitry_tnb_wallet.owner
    bet, _, _ = place_bet(**request(user))
    expire(bet)
    race(
        lambda: accepted(lambda: act(**action(user, bet))),
        lambda: expire_hand(bet_id=bet.pk),
    )
    bet.refresh_from_db()
    dmitry_tnb_wallet.refresh_from_db()
    assert bet.settlement_reason == 'timeout' and bet.result['actions'] == ['draw:11111']
    assert bet.payout == 12 and dmitry_tnb_wallet.balance == 1008
    assert CasinoLedgerEntry.objects.filter(bet=bet, kind='payout').count() == 1
    assert reconcile_fund()['reserved'] == 0
