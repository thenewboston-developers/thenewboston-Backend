from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from thenewboston.authentication.serializers.token import TokenSerializer

from ..serializers.user import UserReadSerializer, UserWriteSerializer


class UserDetailView(APIView):

    @staticmethod
    def post(request):
        serializer = UserWriteSerializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            user = serializer.save()

            response = {
                'authentication': TokenSerializer(user).data,
                'user': UserReadSerializer(user).data,
            }

            return Response(response, status=status.HTTP_201_CREATED)
