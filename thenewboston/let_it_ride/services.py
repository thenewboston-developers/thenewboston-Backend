"""A Let It Ride hand between its deal and its payout. Every writer takes the casino's fund -> bet -> wallet locks."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from thenewboston.casino.fairness import FairRandom, decrypt_seed, seed_hash
from thenewboston.casino.models import MAX_SAFE_INTEGER, CasinoBet
from thenewboston.casino.services import CasinoError, _locked_fund, _publish_wallet, _uuid, pay_out
from thenewboston.wallets.models import Wallet

from . import engine

GAME = 'let_it_ride'


def _verified(bet):
    """Re-deal the hand from its committed seed and replay its decisions; anything else leaves the money alone."""
    seed = decrypt_seed(bet.commitment.encrypted_server_seed)
    if seed_hash(seed) != bet.commitment.server_seed_hash:
        raise RuntimeError('Let It Ride commitment verification failed; reservation retained')
    random = FairRandom(
        server_seed=seed,
        client_seed=bet.client_seed,
        commitment_id=bet.commitment_id,
        game=bet.game,
        rules_version=bet.rules_version,
    )
    try:
        state = engine.replay(*engine.deal(random), bet.result['decisions'], bet.result['action_ids'])
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('Let It Ride transcript verification failed; reservation retained') from exc
    if state != bet.result:
        raise RuntimeError('Let It Ride state verification failed; reservation retained')
    if bet.amount % engine.BETS or bet.total_stake != bet.amount or bet.house_exposure != engine.MAX_ODDS * bet.amount:
        raise RuntimeError('Let It Ride stake verification failed; reservation retained')
    return seed


def _expired(bet):
    return bet.created_date + timedelta(seconds=engine.TIMEOUT_SECONDS) <= timezone.now()


def _finish(*, fund, bet, wallet, seed, reason='completed'):
    """Pay a hand whose last card is turned. A hand still waiting for a decision only saves its state."""
    if bet.result['phase'] != 'settled':
        bet.save(update_fields=['result', 'modified_date'])
        return
    pay_out(
        fund=fund,
        bet=bet,
        wallet=wallet,
        payout=engine.payout(bet.amount, bet.result),
        seed=seed,
        reason=reason,
        update_fields=['result'],
    )
    _publish_wallet(wallet)


def _time_out(*, fund, bet, wallet, seed):
    state = bet.result
    while state['phase'] != 'settled':
        state = engine.apply_action(state, engine.timeout_action(state))
    bet.result = state
    _finish(fund=fund, bet=bet, wallet=wallet, seed=seed, reason='timeout')


@transaction.atomic
def act(*, user, request_id, action_id, action, expected_revision):
    """Decide the next bet: 'ride' leaves it on the table, 'pull' takes it back. Safe to retry with the same ID."""
    request_id, action_id = _uuid(request_id), str(_uuid(action_id))
    if type(expected_revision) is not int or not 0 <= expected_revision < engine.BETS - 1:
        raise CasinoError('A valid hand revision is required.')
    if not isinstance(action, str) or action not in engine.ACTIONS:
        raise CasinoError('Choose Let It Ride or Pull Back.')
    fund = _locked_fund()
    bet = (
        CasinoBet.objects.select_for_update()
        .select_related('commitment')
        .filter(user=user, request_id=request_id, game=GAME, rules_version=1)
        .first()
    )
    if bet is None:
        raise CasinoError('No Let It Ride hand has this request ID.', code='not_found', status=404)
    wallet = Wallet.objects.select_for_update().get(pk=bet.wallet_id)
    # An open hand is checked against its commitment before anything in it is trusted.
    seed = _verified(bet) if bet.status == 'open' else None
    state = bet.result
    if action_id in state['action_ids']:
        index = state['action_ids'].index(action_id)
        if state['decisions'][index] != action or index != expected_revision:
            raise CasinoError('This action ID was used with different details.', code='request_conflict', status=409)
        return bet, fund, wallet
    if bet.status == 'settled':
        raise CasinoError('This hand is already settled. Refresh to see its result.', code='hand_settled', status=409)
    # Decided before the next card is turned, so a full wallet can never selectively reject a winning hand.
    if wallet.balance + bet.protected_amount > MAX_SAFE_INTEGER:
        raise CasinoError('The potential payout would exceed the wallet balance limit.', code='wallet_limit')
    # An overdue hand cannot be played after its deadline, even when the sweep is running late.
    if _expired(bet):
        _time_out(fund=fund, bet=bet, wallet=wallet, seed=seed)
        return bet, fund, wallet
    if state['revision'] != expected_revision:
        raise CasinoError('This hand has changed. Refresh before acting.', code='revision_conflict', status=409)
    bet.result = engine.apply_action(state, action, action_id)
    _finish(fund=fund, bet=bet, wallet=wallet, seed=seed)
    return bet, fund, wallet


@transaction.atomic
def expire_hand(*, bet_id):
    """Trusted worker entry point: finish one overdue hand. Never accepts a client-supplied decision or payout."""
    fund = _locked_fund()
    bet = CasinoBet.objects.select_for_update().select_related('commitment').get(pk=bet_id)
    if bet.game != GAME or bet.rules_version != 1 or bet.status == 'settled' or not _expired(bet):
        return bet
    wallet = Wallet.objects.select_for_update().get(pk=bet.wallet_id)
    _time_out(fund=fund, bet=bet, wallet=wallet, seed=_verified(bet))
    return bet
