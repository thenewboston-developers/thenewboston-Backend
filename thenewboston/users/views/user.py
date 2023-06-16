from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers.user import UserReadSerializer, UserWriteSerializer


class UserDetailView(APIView):

    @staticmethod
    def post(request):
        serializer = UserWriteSerializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            return Response(UserReadSerializer(user).data, status=status.HTTP_201_CREATED)
