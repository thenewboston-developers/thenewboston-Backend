import logging

from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError

from thenewboston.currencies.models import Currency
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.wallets.models import Wallet

from .models import GameFund, GameFundDeposit, GameRewardDecision

REWARD_AMOUNT = 10
MAX_DEPOSIT = 1000000000
MAX_TOTAL = 9007199254740991
logger = logging.getLogger(__name__)


class RequestConflict(APIException):
    status_code = 409
    default_detail = 'This request ID was already used with a different amount.'


def fund_summary(fund=None):
    if fund is None:
        fund = GameFund.objects.filter(pk=1).first()
    balance = fund.balance if fund else 0
    enabled = fund.enabled if fund else True
    return {
        'balance': balance,
        'currency': 'TNB',
        'reward_amount': REWARD_AMOUNT,
        'wins_remaining': balance // REWARD_AMOUNT,
        'total_deposited': fund.total_deposited if fund else 0,
        'total_paid': fund.total_paid if fund else 0,
        'enabled': enabled,
        'available': enabled and balance >= REWARD_AMOUNT,
    }


def _locked_fund():
    # Also handles test database flushes and first use without a currency configured.
    GameFund.objects.get_or_create(pk=1)
    return GameFund.objects.select_for_update().get(pk=1)


def _publish_wallet(wallet):
    def publish():
        try:
            wallet.stream()
        except Exception:
            # The financial transaction has already committed. Polling recovers the display.
            logger.exception('Could not publish game fund wallet update for wallet %s', wallet.pk)

    apply_on_commit(publish)


@transaction.atomic
def contribute(*, user, amount, request_id):
    if type(amount) is not int or not 1 <= amount <= MAX_DEPOSIT:
        raise ValidationError('Contribute a whole number from 1 to 1,000,000,000 TNB.')
    # All contributions and rewards acquire fund first, then wallet, in this order.
    fund = _locked_fund()
    existing = GameFundDeposit.objects.filter(donor=user, request_id=request_id).first()
    if existing:
        if existing.amount != amount:
            raise RequestConflict()
        return existing, fund
    if fund.total_deposited + amount > MAX_TOTAL:
        raise ValidationError('The fund has reached its contribution limit.')
    currency = fund.currency or Currency.objects.filter(ticker='TNB').first()
    if currency is None:
        raise ValidationError('TNB is not configured yet.')
    wallet = Wallet.objects.select_for_update().filter(owner=user, currency=currency).first()
    if wallet is None or wallet.balance < amount:
        raise ValidationError('Insufficient TNB balance for this contribution.')
    wallet.change_balance(-amount, should_stream=False)
    fund.currency = currency
    fund.balance += amount
    fund.total_deposited += amount
    fund.save()
    deposit = GameFundDeposit.objects.create(fund=fund, donor=user, wallet=wallet, request_id=request_id, amount=amount)
    _publish_wallet(wallet)
    return deposit, fund


def _receipt(decision):
    return {'status': decision.status, 'amount': decision.amount, 'currency': 'TNB'}


@transaction.atomic
def settle_computer_reward(*, game, match_id, user_id, won):
    """Only trusted terminal game transitions call this, inside their locked transaction.

    No public claim endpoint exists. Persist the result on the match in that same
    transaction; never call from reads or retry previously completed games.
    """
    if user_id is None:
        # Guest wins are informational only: no fund lock, wallet, ledger or claimable reward.
        fund = GameFund.objects.filter(pk=1).first()
        eligible = bool(won and fund and fund.currency_id and fund.enabled and fund.balance >= REWARD_AMOUNT)
        return {
            'status': 'guest' if eligible else ('fund_empty' if won else 'not_eligible'),
            'amount': REWARD_AMOUNT if eligible else 0,
            'currency': 'TNB',
        }
    if game not in {'connect_five', 'backgammon', 'battleship', 'checkers', 'reversi', 'mancala'}:
        raise ValueError('Unsupported reward game.')
    fund = _locked_fund()
    existing = GameRewardDecision.objects.filter(game=game, match_id=match_id).first()
    if existing:
        if existing.user_id != user_id:
            raise ValueError('The reward decision belongs to another player.')
        return _receipt(existing)
    status = 'not_eligible' if not won else 'fund_empty'
    amount, wallet = 0, None
    if won and fund.enabled and fund.currency_id and fund.balance >= REWARD_AMOUNT:
        # The full Currency object is essential for external TNB deposit-key creation.
        wallet, _ = Wallet.objects.get_or_create(owner_id=user_id, currency=fund.currency, _for_update=True)
        wallet.change_balance(REWARD_AMOUNT, should_stream=False)
        fund.balance -= REWARD_AMOUNT
        fund.total_paid += REWARD_AMOUNT
        fund.save()
        status, amount = 'paid', REWARD_AMOUNT
    decision = GameRewardDecision.objects.create(
        fund=fund, user_id=user_id, wallet=wallet, game=game, match_id=match_id, status=status, amount=amount
    )
    if wallet:
        _publish_wallet(wallet)
    return _receipt(decision)
