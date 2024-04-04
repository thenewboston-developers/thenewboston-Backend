from thenewboston.cores.utils.core import get_default_core
from thenewboston.wallets.models.wallet import Wallet


def get_default_wallet(user):
    return Wallet.objects.filter(owner=user, core=get_default_core()).first()
