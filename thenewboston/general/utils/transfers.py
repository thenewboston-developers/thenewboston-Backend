from django.db import transaction

from thenewboston.general.enums import MessageType
from thenewboston.general.exceptions import ProgrammingError
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.serializers.wallet import WalletReadSerializer


def stream_wallet_update(wallet):
    WalletConsumer.stream_wallet(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data=WalletReadSerializer(wallet).data,
    )


def change_wallet_balance(wallet, amount, allow_outside_atomic_block=False):
    is_in_atomic_block = transaction.get_connection().in_atomic_block
    if not is_in_atomic_block and not allow_outside_atomic_block:
        raise ProgrammingError('Not allowed to run outside atomic block')

    wallet.balance += amount
    wallet.save()

    if is_in_atomic_block:
        apply_on_commit(lambda: stream_wallet_update(wallet))
    else:
        stream_wallet_update(wallet)


def transfer_coins(*, sender_wallet, recipient_wallet, amount):
    assert transaction.get_connection().in_atomic_block

    change_wallet_balance(sender_wallet, -amount)
    change_wallet_balance(recipient_wallet, amount)
