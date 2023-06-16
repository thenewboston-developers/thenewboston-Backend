from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from thenewboston.users.serializers.user import UserReadSerializer

from ..serializers.login import LoginSerializer


class LoginView(APIView):

    @staticmethod
    def post(request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)

        response = {
            'authentication': {
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
            },
            'user': UserReadSerializer(user).data,
        }

        return Response(response, status=status.HTTP_200_OK)
