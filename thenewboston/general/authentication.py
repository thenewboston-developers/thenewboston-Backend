from thenewboston.authentication.serializers.token import TokenSerializer
from thenewboston.users.serializers.user import UserReadSerializer


def get_user_auth_data(user, request):
    return {
        'authentication': TokenSerializer(user).data,
        'user': UserReadSerializer(user, context={
            'request': request
        }).data,
    }
