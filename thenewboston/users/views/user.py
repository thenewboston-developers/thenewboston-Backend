from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from thenewboston.general.authentication import get_user_auth_data

from ..serializers.user import UserWriteSerializer


class UserDetailView(APIView):

    @staticmethod
    def post(request):
        serializer = UserWriteSerializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            return Response(get_user_auth_data(user), status=status.HTTP_201_CREATED)
