from thenewboston.general.enums import MessageType
from thenewboston.wallets.consumers.wallet import WalletConsumer
from thenewboston.wallets.serializers.wallet import WalletReadSerializer


def transfer_coins(*, amount, recipient_wallet, sender_wallet):
    sender_wallet.balance -= amount
    recipient_wallet.balance += amount
    sender_wallet.save()
    recipient_wallet.save()

    sender_wallet_data = WalletReadSerializer(sender_wallet).data
    WalletConsumer.stream_wallet(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data=sender_wallet_data,
    )

    recipient_wallet_data = WalletReadSerializer(recipient_wallet).data
    WalletConsumer.stream_wallet(
        message_type=MessageType.UPDATE_WALLET,
        wallet_data=recipient_wallet_data,
    )
