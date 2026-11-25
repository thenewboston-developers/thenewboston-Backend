import hashlib
import json
import logging
from datetime import timedelta
from functools import partial
from uuid import UUID

from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Sum, When
from django.utils import timezone

from thenewboston.currencies.models import Currency
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.wallets.models import Wallet

from .fairness import ALGORITHM, FairRandom, decrypt_seed, encrypt_seed, generate_seed, seed_hash
from .models import MAX_SAFE_INTEGER, CasinoBet, CasinoCommitment, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from .registry import get_rules, registry

MAX_AMOUNT = 1000000000
logger = logging.getLogger(__name__)


class CasinoError(Exception):
    def __init__(self, detail, *, code='invalid_request', status=400, **extra):
        self.data = {'code': code, 'detail': detail, **extra}
        self.status = status
        super().__init__(detail)


def _amount(amount):
    if type(amount) is not int or not 1 <= amount <= MAX_AMOUNT:
        raise CasinoError(f'Enter a whole number from 1 to {MAX_AMOUNT:,} TNB.')


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise CasinoError('A valid request or commitment ID is required.') from exc


def _locked_fund():
    CasinoFund.objects.get_or_create(pk=1)
    return CasinoFund.objects.select_for_update().get(pk=1)


def fund_summary(fund=None):
    fund = fund if fund is not None else CasinoFund.objects.filter(pk=1).first()
    return {
        'balance': fund.balance if fund else 0,
        'reserved': fund.reserved if fund else 0,
        'available': fund.available if fund else 0,
        'currency': 'TNB',
        'enabled': fund.enabled if fund else True,
        'risk_limit_bps': fund.risk_limit_bps if fund else 100,
    }


def risk_capacity(fund):
    # The most one wager may cost the casino. Determined BEFORE crediting the incoming stake: never count it twice.
    return fund['available'] * fund['risk_limit_bps'] // 10000


def max_bet(fund, multiplier):
    return min(MAX_AMOUNT, risk_capacity(fund) // (multiplier - 1), MAX_SAFE_INTEGER - fund['balance'])


def casino_summary(user=None):
    fund = fund_summary()
    configs = {config.game: config for config in CasinoGameConfig.objects.all()}
    games = []
    for definition in registry.games:
        game = definition.game
        config = configs.get(game)
        version = config.rules_version if config else definition.default_version
        rules = registry.rules.get((game, version))
        enabled = bool(config and config.enabled and rules)
        if rules is None:
            rules = get_rules(game, definition.default_version)
        minimum = config.min_bet if config else definition.default_min_bet
        maximum = max_bet(fund, rules.catalog_multiplier)
        entry = {
            'id': game,
            'name': rules.name,
            'enabled': enabled,
            'available': enabled and fund['enabled'] and maximum >= minimum,
            'min_bet': minimum,
            'max_bet': maximum,
            'max_multiplier': rules.max_multiplier,
            'rules_version': version,
            'house_edge': rules.house_edge,
        }
        entry.update(rules.catalog_data(partial(max_bet, fund)))
        games.append(entry)
    return {'fund': fund, 'games': games, 'can_manage': bool(user and user.is_authenticated and user.is_staff)}


def _publish_wallet(wallet):
    def publish():
        try:
            wallet.stream()
        except Exception:
            logger.exception('Casino wallet broadcast failed for wallet %s; polling can recover', wallet.pk)

    apply_on_commit(publish)


def _ledger(fund, wallet, kind, amount, *, bet=None, request_id=None):
    return CasinoLedgerEntry.objects.create(
        fund=fund,
        user_id=wallet.owner_id,
        wallet=wallet,
        kind=kind,
        amount=amount,
        bet=bet,
        request_id=request_id,
        event_key=kind if bet else '',
    )


@transaction.atomic
def create_commitment(*, user):
    # Serializes creation too: at most one unexpired unused commitment per user, avoiding request spam growth.
    _locked_fund()
    now = timezone.now()
    existing = CasinoCommitment.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).first()
    if existing:
        return existing
    seed = generate_seed()
    return CasinoCommitment.objects.create(
        user=user,
        server_seed_hash=seed_hash(seed),
        encrypted_server_seed=encrypt_seed(seed),
        expires_at=now + timedelta(minutes=10),
    )


def commitment_receipt(commitment):
    return {
        'id': str(commitment.id),
        'server_seed_hash': commitment.server_seed_hash,
        'expires_at': commitment.expires_at,
        'algorithm': ALGORITHM,
    }


def bet_receipt(bet, *, fund=None, wallet_balance=None):
    return {
        'id': bet.pk,
        'request_id': str(bet.request_id),
        'game': bet.game,
        'amount': bet.amount,
        'total_stake': bet.total_stake,
        'status': bet.status,
        'selection': bet.selection,
        'payout': bet.payout,
        'profit': bet.payout - bet.total_stake if bet.status == 'settled' else None,
        'result': bet.result if bet.status == 'settled' else {},
        'rules_version': bet.rules_version,
        'created_at': bet.created_date,
        'settled_at': bet.settled_at,
        'fairness': {
            'commitment_id': str(bet.commitment_id),
            'server_seed_hash': bet.commitment.server_seed_hash,
            'server_seed': bet.revealed_server_seed or None,
            'client_seed': bet.client_seed,
            'algorithm': ALGORITHM,
        },
        'fund': fund_summary(fund),
        'wallet_balance': wallet_balance
        if wallet_balance is not None
        else Wallet.objects.values_list('balance', flat=True).get(pk=bet.wallet_id),
    }


@transaction.atomic
def move_funds(*, user, amount, request_id, kind):
    if not user.is_staff:
        raise CasinoError('Only an administrator can move casino funds.', code='permission_denied', status=403)
    _amount(amount)
    if kind not in ('deposit', 'withdrawal'):
        raise CasinoError('Unsupported fund movement.')
    request_id = _uuid(request_id)
    fund = _locked_fund()
    existing = CasinoLedgerEntry.objects.filter(user=user, request_id=request_id).first()
    if existing:
        if existing.amount != amount or existing.kind != kind:
            raise CasinoError('This request ID was used with different details.', code='request_conflict', status=409)
        return existing, fund, Wallet.objects.get(pk=existing.wallet_id)
    currency = fund.currency or Currency.objects.filter(ticker='TNB').first()
    if currency is None:
        raise CasinoError('TNB is not configured.', code='currency_unavailable')
    wallet = Wallet.objects.select_for_update().filter(owner=user, currency=currency).first()
    if wallet is None:
        raise CasinoError('A TNB wallet is required.', code='wallet_unavailable')
    if kind == 'deposit':
        if wallet.balance < amount:
            raise CasinoError('Insufficient TNB balance.', code='insufficient_balance')
        if fund.balance + amount > MAX_SAFE_INTEGER:
            raise CasinoError('The casino balance limit would be exceeded.', code='fund_limit')
        fund.balance += amount
        wallet.change_balance(-amount, should_stream=False)
    else:
        if amount > fund.available:
            raise CasinoError(
                'Only unreserved funds can be withdrawn.',
                code='funds_reserved',
                max_amount=fund.available,
                fund=fund_summary(fund),
            )
        if wallet.balance + amount > MAX_SAFE_INTEGER:
            raise CasinoError('The wallet balance limit would be exceeded.', code='wallet_limit')
        fund.balance -= amount
        wallet.change_balance(amount, should_stream=False)
    fund.currency = currency
    fund.save(update_fields=['balance', 'currency', 'modified_date'])
    entry = _ledger(fund, wallet, kind, amount, request_id=request_id)
    _publish_wallet(wallet)
    return entry, fund, wallet


def _settle_locked(*, fund, bet, wallet):
    if bet.status == 'settled':
        return bet
    rules = get_rules(bet.game, bet.rules_version)
    if rules.settlement_mode != 'instant':
        raise RuntimeError('This game requires its own interactive settlement handler')
    seed = decrypt_seed(bet.commitment.encrypted_server_seed)
    if seed_hash(seed) != bet.commitment.server_seed_hash:
        raise RuntimeError('Casino commitment verification failed; reservation retained')
    random = FairRandom(
        server_seed=seed,
        client_seed=bet.client_seed,
        commitment_id=bet.commitment_id,
        game=bet.game,
        rules_version=bet.rules_version,
    )
    expected = rules.outcome(random, bet.selection)
    if expected != bet.result:
        raise RuntimeError('Casino result verification failed; reservation retained')
    payout = rules.payout(bet.amount, bet.result)
    protected = bet.protected_amount
    if payout > protected or fund.reserved < protected or wallet.balance + payout > MAX_SAFE_INTEGER:
        raise RuntimeError('Casino settlement invariant failed; reservation retained')
    fund.balance -= payout
    fund.reserved -= protected
    fund.save(update_fields=['balance', 'reserved', 'modified_date'])
    wallet.change_balance(payout, should_stream=False)
    bet.payout = payout
    bet.status = 'settled'
    bet.settlement_reason = 'completed'
    bet.settled_at = timezone.now()
    bet.revealed_server_seed = seed
    bet.save(
        update_fields=['payout', 'status', 'settlement_reason', 'settled_at', 'revealed_server_seed', 'modified_date']
    )
    _ledger(fund, wallet, 'payout', payout, bet=bet)
    return bet


@transaction.atomic
def place_bet(*, user, request_id, commitment_id, client_seed, game, amount, selection=None, rules_version=1):
    _amount(amount)
    request_id, commitment_id = _uuid(request_id), _uuid(commitment_id)
    if type(rules_version) is not int or not isinstance(client_seed, str) or not 1 <= len(client_seed) <= 128:
        raise CasinoError('Invalid rules version or client seed.')
    if not client_seed.isascii() or any(ord(character) < 32 or ord(character) > 126 for character in client_seed):
        raise CasinoError('Client seed must contain printable ASCII characters.')
    try:
        rules = get_rules(game, rules_version)
        selection = rules.prepare_selection(selection, amount)
    except ValueError as exc:
        raise CasinoError(str(exc)) from exc
    payload = [game, rules_version, amount, selection, str(commitment_id), client_seed]
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    fund = _locked_fund()
    existing = CasinoBet.objects.select_for_update().filter(user=user, request_id=request_id).first()
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise CasinoError('This request ID was used with different details.', code='request_conflict', status=409)
        return existing, fund, Wallet.objects.get(pk=existing.wallet_id)
    config = CasinoGameConfig.objects.select_for_update().filter(pk=game).first()
    if not fund.enabled:
        raise CasinoError('Casino wagering is temporarily closed.', code='casino_closed', fund=fund_summary(fund))
    if config is None or not config.enabled:
        raise CasinoError('This game is temporarily closed.', code='game_closed', fund=fund_summary(fund))
    if config.rules_version != rules_version:
        raise CasinoError('The game rules changed. Refresh before betting.', code='rules_changed', status=409)
    limits = fund_summary(fund)
    # The casino's worst case decides the limit, so a wager spread over several outcomes is judged as a whole.
    exposure = rules.exposure(selection, amount)
    if amount < config.min_bet or exposure > risk_capacity(limits) or amount > MAX_SAFE_INTEGER - fund.balance:
        raise CasinoError(
            'The wager is outside the currently permitted range.',
            code='bet_limit',
            min_bet=config.min_bet,
            max_bet=max_bet(limits, rules.multiplier(selection)),
            fund=limits,
        )
    if CasinoBet.objects.filter(user=user, status='open').exists():
        raise CasinoError('Finish the existing casino game first.', code='game_in_progress', status=409)
    commitment = CasinoCommitment.objects.select_for_update().filter(pk=commitment_id, user=user).first()
    if commitment is None or commitment.used_at or commitment.expires_at <= timezone.now():
        raise CasinoError('Prepare a new fairness commitment before betting.', code='commitment_unavailable')
    if fund.currency_id is None:
        raise CasinoError('The casino has not been funded.', code='casino_unfunded')
    wallet = Wallet.objects.select_for_update().filter(owner=user, currency_id=fund.currency_id).first()
    if wallet is None or wallet.balance < amount:
        raise CasinoError('Insufficient TNB balance.', code='insufficient_balance')
    # These checks occur before deriving any outcome, so near-limit balances cannot selectively reject wins.
    if wallet.balance + exposure > MAX_SAFE_INTEGER:
        raise CasinoError('The potential payout would exceed the wallet balance limit.', code='wallet_limit')
    if fund.balance + amount > MAX_SAFE_INTEGER:
        raise CasinoError('The wager would exceed the casino balance limit.', code='fund_limit')
    wallet.change_balance(-amount, should_stream=False)
    fund.balance += amount
    fund.reserved += amount + exposure
    fund.save(update_fields=['balance', 'reserved', 'modified_date'])
    commitment.used_at = timezone.now()
    commitment.save(update_fields=['used_at', 'modified_date'])
    seed = decrypt_seed(commitment.encrypted_server_seed)
    random = FairRandom(
        server_seed=seed, client_seed=client_seed, commitment_id=commitment.id, game=game, rules_version=rules_version
    )
    bet = CasinoBet.objects.create(
        fund=fund,
        user=user,
        wallet=wallet,
        request_id=request_id,
        request_fingerprint=fingerprint,
        game=game,
        rules_version=rules_version,
        amount=amount,
        total_stake=amount,
        house_exposure=exposure,
        selection=selection,
        commitment=commitment,
        client_seed=client_seed,
        result=rules.outcome(random, selection),
    )
    _ledger(fund, wallet, 'stake', amount, bet=bet)
    _settle_locked(fund=fund, bet=bet, wallet=wallet)
    _publish_wallet(wallet)
    return bet, fund, wallet


@transaction.atomic
def settle_bet(*, bet_id):
    """Trusted worker entry point. Never accepts a client-supplied outcome or payout."""
    fund = _locked_fund()
    bet = CasinoBet.objects.select_for_update().select_related('commitment').get(pk=bet_id)
    if bet.status == 'settled':
        return bet
    wallet = Wallet.objects.select_for_update().get(pk=bet.wallet_id)
    _settle_locked(fund=fund, bet=bet, wallet=wallet)
    _publish_wallet(wallet)
    return bet


@transaction.atomic
def reconcile_fund():
    """Read-only reconciliation under the same fund lock as every financial writer."""
    fund = CasinoFund.objects.select_for_update().filter(pk=1).first()
    if fund is None:
        return {'balance': 0, 'reserved': 0, 'ledger_balance': 0, 'expected_reserved': 0, 'open_bets': 0}
    ledger_balance = (
        CasinoLedgerEntry.objects.filter(fund=fund).aggregate(
            total=Sum(
                Case(
                    When(kind__in=['deposit', 'stake'], then=F('amount')),
                    default=-F('amount'),
                    output_field=IntegerField(),
                )
            )
        )['total']
        or 0
    )
    open_bets = CasinoBet.objects.filter(fund=fund, status='open')
    expected_reserved = open_bets.aggregate(total=Sum(F('total_stake') + F('house_exposure')))['total'] or 0
    missing_stakes = CasinoBet.objects.filter(fund=fund).exclude(casinoledgerentry__kind='stake').exists()
    missing_payouts = (
        CasinoBet.objects.filter(fund=fund, status='settled').exclude(casinoledgerentry__kind='payout').exists()
    )
    bad_stakes = (
        CasinoBet.objects.filter(fund=fund)
        .annotate(ledger_stakes=Sum('casinoledgerentry__amount', filter=Q(casinoledgerentry__kind='stake')))
        .exclude(total_stake=F('ledger_stakes'))
        .exists()
    )
    bad_payouts = CasinoLedgerEntry.objects.filter(kind='payout').exclude(amount=F('bet__payout')).exists()
    if (
        fund.balance != ledger_balance
        or fund.reserved != expected_reserved
        or any((missing_stakes, missing_payouts, bad_stakes, bad_payouts))
    ):
        raise RuntimeError('Casino ledger or reservation reconciliation failed')
    return {
        'balance': fund.balance,
        'reserved': fund.reserved,
        'ledger_balance': ledger_balance,
        'expected_reserved': expected_reserved,
        'open_bets': open_bets.count(),
    }
