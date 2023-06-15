from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers.user import UserSerializer


class UserDetailView(APIView):

    @staticmethod
    def post(request):
        serializer = UserSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            if user:
                return Response(status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
