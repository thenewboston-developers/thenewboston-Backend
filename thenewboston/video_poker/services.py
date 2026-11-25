"""Interactive play uses the casino's fund -> bet -> wallet lock order, including timeout workers."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from thenewboston.casino.fairness import FairRandom, decrypt_seed, seed_hash
from thenewboston.casino.models import MAX_SAFE_INTEGER, CasinoBet
from thenewboston.casino.services import CasinoError, _locked_fund, _publish_wallet, _uuid, pay_out
from thenewboston.wallets.models import Wallet

from . import engine
from .models import VideoPokerDraw

GAME = 'video_poker'


def _verified(bet):
    seed = decrypt_seed(bet.commitment.encrypted_server_seed)
    if seed_hash(seed) != bet.commitment.server_seed_hash:
        raise RuntimeError('Video Poker commitment verification failed; reservation retained')
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
        raise RuntimeError('Video Poker transcript verification failed; reservation retained') from exc
    if state != bet.result or bet.total_stake != bet.amount:
        raise RuntimeError('Video Poker state verification failed; reservation retained')
    if bet.house_exposure != (engine.MAX_MULTIPLIER - 1) * bet.amount:
        raise RuntimeError('Video Poker exposure verification failed; reservation retained')
    return seed, deck


def verify_deal(bet):
    """Acceptance hook: the hand stays open until the player draws, so nothing settles here."""
    _verified(bet)


def _settle(*, fund, bet, wallet, seed, reason='completed'):
    if bet.status == 'settled' or bet.result['phase'] != 'settled':
        return
    pay_out(
        fund=fund,
        bet=bet,
        wallet=wallet,
        payout=bet.amount * bet.result['multiplier'],
        seed=seed,
        reason=reason,
        update_fields=['result'],
    )


def _expired(bet):
    return bet.created_date + timedelta(seconds=engine.TIMEOUT_SECONDS) <= timezone.now()


def _check_wallet_capacity(bet, wallet, error):
    # Checked before any replacement card is derived, so a full wallet can never reject only winning draws.
    if wallet.balance + engine.MAX_MULTIPLIER * bet.amount > MAX_SAFE_INTEGER:
        raise error


def _timeout_locked(*, fund, bet, wallet):
    _check_wallet_capacity(
        bet, wallet, RuntimeError('Video Poker wallet capacity is unavailable; reservation retained')
    )
    seed, deck = _verified(bet)
    # Nobody chose discards, so the dealt hand stands exactly as it was dealt.
    bet.result = engine.apply_action(bet.result, deck, engine.STAND_PAT)
    _settle(fund=fund, bet=bet, wallet=wallet, seed=seed, reason='timeout')


@transaction.atomic
def act(*, user, request_id, action_id, action, expected_revision):
    request_id, action_id = _uuid(request_id), _uuid(action_id)
    if type(expected_revision) is not int or expected_revision not in (0, 1):
        raise CasinoError('A valid hand revision is required.')
    try:
        engine.parse_action(action)
    except ValueError as exc:
        raise CasinoError(str(exc)) from exc
    fund = _locked_fund()
    bet = (
        CasinoBet.objects.select_for_update()
        .select_related('commitment')
        .filter(user=user, request_id=request_id, game=GAME, rules_version=1)
        .first()
    )
    if bet is None:
        raise CasinoError('No Video Poker hand has this request ID.', code='not_found', status=404)
    existing = VideoPokerDraw.objects.filter(bet=bet, action_id=action_id).first()
    if existing:
        if existing.action != action or expected_revision != 0:
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
    _check_wallet_capacity(
        bet, wallet, CasinoError('The potential payout would exceed the wallet balance limit.', code='wallet_limit')
    )
    seed, deck = _verified(bet)
    bet.result = engine.apply_action(bet.result, deck, action)
    VideoPokerDraw.objects.create(bet=bet, action_id=action_id, action=action)
    _settle(fund=fund, bet=bet, wallet=wallet, seed=seed)
    _publish_wallet(wallet)
    return bet, fund, wallet


@transaction.atomic
def expire_hand(*, bet_id):
    fund = _locked_fund()
    bet = CasinoBet.objects.select_for_update().select_related('commitment').get(pk=bet_id)
    if bet.game != GAME or bet.rules_version != 1 or bet.status == 'settled' or not _expired(bet):
        return bet
    wallet = Wallet.objects.select_for_update().get(pk=bet.wallet_id)
    _timeout_locked(fund=fund, bet=bet, wallet=wallet)
    _publish_wallet(wallet)
    return bet
