"""Interactive play uses the casino's fund -> bet -> wallet lock order, including timeout workers."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from thenewboston.casino.fairness import FairRandom, decrypt_seed, seed_hash
from thenewboston.casino.models import MAX_SAFE_INTEGER, CasinoBet, CasinoLedgerEntry
from thenewboston.casino.services import CasinoError, _ledger, _locked_fund, _publish_wallet, _uuid
from thenewboston.wallets.models import Wallet

from . import engine
from .models import BlackjackAction


def _verified(bet):
    seed = decrypt_seed(bet.commitment.encrypted_server_seed)
    if seed_hash(seed) != bet.commitment.server_seed_hash:
        raise RuntimeError('Blackjack commitment verification failed; reservation retained')
    random = FairRandom(
        server_seed=seed,
        client_seed=bet.client_seed,
        commitment_id=bet.commitment_id,
        game=bet.game,
        rules_version=bet.rules_version,
    )
    deck = engine.shuffled_deck(random)
    try:
        state = engine.replay(deck, bet.result['actions'])
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('Blackjack transcript verification failed; reservation retained') from exc
    if state != bet.result or bet.total_stake != bet.amount * (2 if state['doubled'] else 1):
        raise RuntimeError('Blackjack state verification failed; reservation retained')
    if bet.house_exposure != 2 * bet.amount:
        raise RuntimeError('Blackjack exposure verification failed; reservation retained')
    return seed, deck


def _settle(*, fund, bet, wallet, seed, reason='completed'):
    if bet.status == 'settled' or bet.result['phase'] != 'settled':
        return
    # Integer arithmetic only, even when the published total-return multiplier is 2.5.
    payout = bet.amount * 5 // 2 if bet.result['outcome'] == 'blackjack' else bet.amount * bet.result['multiplier']
    protected = bet.protected_amount
    if (
        type(payout) is not int
        or payout > protected
        or fund.reserved < protected
        or wallet.balance + payout > MAX_SAFE_INTEGER
    ):
        raise RuntimeError('Blackjack settlement invariant failed; reservation retained')
    fund.balance -= payout
    fund.reserved -= protected
    fund.save(update_fields=['balance', 'reserved', 'modified_date'])
    wallet.change_balance(payout, should_stream=False)
    bet.payout = payout
    bet.status = 'settled'
    bet.settlement_reason = reason
    bet.settled_at = timezone.now()
    bet.revealed_server_seed = seed
    bet.save(
        update_fields=[
            'result',
            'total_stake',
            'payout',
            'status',
            'settlement_reason',
            'settled_at',
            'revealed_server_seed',
            'modified_date',
        ]
    )
    _ledger(fund, wallet, 'payout', payout, bet=bet)


def settle_initial(*, fund, bet, wallet):
    seed, _ = _verified(bet)
    _settle(fund=fund, bet=bet, wallet=wallet, seed=seed)


def _expired(bet):
    return bet.created_date + timedelta(seconds=engine.TIMEOUT_SECONDS) <= timezone.now()


def _timeout_locked(*, fund, bet, wallet):
    if wallet.balance + 2 * bet.amount > MAX_SAFE_INTEGER:
        raise RuntimeError('Blackjack wallet capacity is unavailable; reservation retained')
    seed, deck = _verified(bet)
    if bet.result['phase'] != 'settled':
        bet.result = engine.apply_action(bet.result, deck, 'stand')
    _settle(fund=fund, bet=bet, wallet=wallet, seed=seed, reason='timeout')


@transaction.atomic
def act(*, user, request_id, action_id, action, expected_revision):
    request_id, action_id = _uuid(request_id), _uuid(action_id)
    if type(expected_revision) is not int or not 0 <= expected_revision <= 21:
        raise CasinoError('A valid hand revision is required.')
    if not isinstance(action, str) or action not in ('hit', 'stand', 'double'):
        raise CasinoError('Select Hit, Stand or Double Down.')
    fund = _locked_fund()
    bet = (
        CasinoBet.objects.select_for_update()
        .select_related('commitment')
        .filter(user=user, request_id=request_id, game='blackjack', rules_version=1)
        .first()
    )
    if bet is None:
        raise CasinoError('No Blackjack hand has this request ID.', code='not_found', status=404)
    existing = BlackjackAction.objects.filter(bet=bet, action_id=action_id).first()
    if existing:
        if existing.action != action or existing.expected_revision != expected_revision:
            raise CasinoError('This action ID was used with different details.', code='request_conflict', status=409)
        return bet, fund, Wallet.objects.get(pk=bet.wallet_id)
    wallet = Wallet.objects.select_for_update().get(pk=bet.wallet_id)
    if bet.status == 'settled':
        raise CasinoError('This hand is already settled. Refresh to see its result.', code='hand_settled', status=409)
    # An overdue hand cannot be played after its deadline, even when the worker is delayed.
    if _expired(bet):
        _timeout_locked(fund=fund, bet=bet, wallet=wallet)
        _publish_wallet(wallet)
        return bet, fund, wallet
    if bet.result['revision'] != expected_revision:
        raise CasinoError('This hand has changed. Refresh before acting.', code='revision_conflict', status=409)
    if action not in engine.available_actions(bet.result):
        raise CasinoError('That action is not available for this hand.', code='action_unavailable')
    # Check numerical limits before deriving a future card, never selectively reject a winning outcome.
    potential_net_credit = (3 if action == 'double' else 2) * bet.amount
    if wallet.balance + potential_net_credit > MAX_SAFE_INTEGER:
        raise CasinoError('The potential payout would exceed the wallet balance limit.', code='wallet_limit')
    if action == 'double':
        if wallet.balance < bet.amount:
            raise CasinoError('Insufficient TNB balance to double down.', code='insufficient_balance')
        if fund.balance + bet.amount > MAX_SAFE_INTEGER:
            raise CasinoError('The additional stake would exceed the casino balance limit.', code='fund_limit')
    seed, deck = _verified(bet)
    state = engine.apply_action(bet.result, deck, action)
    if action == 'double':
        wallet.change_balance(-bet.amount, should_stream=False)
        fund.balance += bet.amount
        fund.reserved += bet.amount
        fund.save(update_fields=['balance', 'reserved', 'modified_date'])
        bet.total_stake += bet.amount
        CasinoLedgerEntry.objects.create(
            fund=fund,
            user=user,
            wallet=wallet,
            bet=bet,
            kind='stake',
            amount=bet.amount,
            event_key=f'action:{action_id}',
        )
    bet.result = state
    BlackjackAction.objects.create(bet=bet, action_id=action_id, action=action, expected_revision=expected_revision)
    bet.save(update_fields=['result', 'total_stake', 'modified_date'])
    _settle(fund=fund, bet=bet, wallet=wallet, seed=seed)
    _publish_wallet(wallet)
    return bet, fund, wallet


@transaction.atomic
def expire_hand(*, bet_id):
    fund = _locked_fund()
    bet = CasinoBet.objects.select_for_update().select_related('commitment').get(pk=bet_id)
    if bet.game != 'blackjack' or bet.rules_version != 1 or bet.status == 'settled' or not _expired(bet):
        return bet
    wallet = Wallet.objects.select_for_update().get(pk=bet.wallet_id)
    _timeout_locked(fund=fund, bet=bet, wallet=wallet)
    _publish_wallet(wallet)
    return bet
