from django.conf import settings
from rest_framework.exceptions import ValidationError

from thenewboston.currencies.models import Currency
from thenewboston.wallets.models import Wallet

from ..enums import EscrowStatus, LedgerAction, LedgerDirection
from ..models import ConnectFiveEscrow, ConnectFiveLedgerEntry


class EscrowAlreadySettledError(ValidationError):
    status_code = 409


def get_default_currency():
    return Currency.objects.get(ticker=settings.DEFAULT_CURRENCY_TICKER)


def get_wallet_for_update(*, user, currency):
    wallet = Wallet.objects.select_for_update().filter(owner=user, currency=currency).first()
    if not wallet:
        raise ValidationError({'detail': 'Wallet not found for default currency.'})
    return wallet


def create_escrow(*, challenge):
    return ConnectFiveEscrow.objects.create(
        challenge=challenge,
        currency=challenge.currency,
        player_a=challenge.challenger,
        player_b=challenge.opponent,
    )


def debit_wallet(*, wallet, escrow, amount, action):
    wallet.change_balance(-amount, should_stream=True)
    ConnectFiveLedgerEntry.objects.create(
        escrow=escrow,
        wallet=wallet,
        amount=amount,
        direction=LedgerDirection.DEBIT,
        action=action,
    )


def credit_wallet(*, wallet, escrow, amount, action):
    wallet.change_balance(amount, should_stream=True)
    ConnectFiveLedgerEntry.objects.create(
        escrow=escrow,
        wallet=wallet,
        amount=amount,
        direction=LedgerDirection.CREDIT,
        action=action,
    )


def apply_contribution(*, escrow, user, amount):
    if user.id == escrow.player_a_id:
        escrow.player_a_contrib += amount
    elif user.id == escrow.player_b_id:
        escrow.player_b_contrib += amount
    else:
        raise ValidationError({'detail': 'User is not part of this escrow.'})

    escrow.total = escrow.player_a_contrib + escrow.player_b_contrib
    escrow.save(update_fields=['player_a_contrib', 'player_b_contrib', 'total', 'modified_date'])


def lock_stake(*, escrow, wallet, amount):
    debit_wallet(
        wallet=wallet,
        escrow=escrow,
        amount=amount,
        action=LedgerAction.STAKE_LOCK,
    )
    apply_contribution(escrow=escrow, user=wallet.owner, amount=amount)


def accept_stake(*, escrow, wallet, amount):
    debit_wallet(
        wallet=wallet,
        escrow=escrow,
        amount=amount,
        action=LedgerAction.STAKE_ACCEPT,
    )
    apply_contribution(escrow=escrow, user=wallet.owner, amount=amount)


def purchase_special(*, escrow, wallet, amount):
    debit_wallet(
        wallet=wallet,
        escrow=escrow,
        amount=amount,
        action=LedgerAction.PURCHASE,
    )
    apply_contribution(escrow=escrow, user=wallet.owner, amount=amount)


def refund_challenge(*, escrow, wallet):
    if escrow.status == EscrowStatus.SETTLED:
        raise EscrowAlreadySettledError({'detail': 'Escrow already settled.'})

    credit_wallet(wallet=wallet, escrow=escrow, amount=escrow.total, action=LedgerAction.CHALLENGE_REFUND)
    escrow.status = EscrowStatus.SETTLED
    escrow.save(update_fields=['status', 'modified_date'])


def settle_draw(*, escrow, wallet_a, wallet_b):
    if escrow.status == EscrowStatus.SETTLED:
        raise EscrowAlreadySettledError({'detail': 'Escrow already settled.'})

    if escrow.player_a_contrib:
        credit_wallet(
            wallet=wallet_a,
            escrow=escrow,
            amount=escrow.player_a_contrib,
            action=LedgerAction.DRAW_REFUND,
        )
    if escrow.player_b_contrib:
        credit_wallet(
            wallet=wallet_b,
            escrow=escrow,
            amount=escrow.player_b_contrib,
            action=LedgerAction.DRAW_REFUND,
        )

    escrow.status = EscrowStatus.SETTLED
    escrow.save(update_fields=['status', 'modified_date'])


def settle_win(*, escrow, wallet, amount):
    if escrow.status == EscrowStatus.SETTLED:
        raise EscrowAlreadySettledError({'detail': 'Escrow already settled.'})

    credit_wallet(wallet=wallet, escrow=escrow, amount=amount, action=LedgerAction.WIN_PAYOUT)
    escrow.status = EscrowStatus.SETTLED
    escrow.save(update_fields=['status', 'modified_date'])
