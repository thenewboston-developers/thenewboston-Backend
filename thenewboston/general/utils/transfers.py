from django.db import transaction

from thenewboston.general.enums import MessageType
from thenewboston.general.exceptions import ProgrammingError
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.serializers.wallet import WalletReadSerializer


def stream_wallet_update(wallet, request):
    WalletConsumer.stream_wallet(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data=WalletReadSerializer(wallet, context={
            'request': request
        }).data,
    )


def change_wallet_balance(wallet, amount, request, allow_outside_atomic_block=False):
    is_in_atomic_block = transaction.get_connection().in_atomic_block
    if not is_in_atomic_block and not allow_outside_atomic_block:
        raise ProgrammingError('Not allowed to run outside atomic block')

    wallet.balance += amount
    wallet.save()

    if is_in_atomic_block:
        apply_on_commit(lambda: stream_wallet_update(wallet, request))
    else:
        stream_wallet_update(wallet, request)


def transfer_coins(*, sender_wallet, recipient_wallet, amount, request):
    assert transaction.get_connection().in_atomic_block

    change_wallet_balance(sender_wallet, -amount, request)
    change_wallet_balance(recipient_wallet, amount, request)
