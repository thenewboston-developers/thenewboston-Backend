from thenewboston.currencies.utils.currency import get_default_currency
from thenewboston.wallets.models.wallet import Wallet


def get_default_wallet(user):
    return Wallet.objects.filter(owner=user, currency=get_default_currency()).first()
