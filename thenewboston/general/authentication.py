from thenewboston.authentication.serializers.token import TokenSerializer
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.serializers.deposit_account import DepositAccountSerializer


def get_user_auth_data(user):
    return {
        'authentication': TokenSerializer(user).data,
        'deposit_account': DepositAccountSerializer(user).data,
        'user': UserReadSerializer(user).data,
    }
