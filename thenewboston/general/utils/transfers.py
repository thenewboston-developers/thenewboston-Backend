from django.db import transaction


def transfer_coins(*, sender_wallet, recipient_wallet, amount):
    assert transaction.get_connection().in_atomic_block

    sender_wallet.change_balance(-amount)
    recipient_wallet.change_balance(amount)
