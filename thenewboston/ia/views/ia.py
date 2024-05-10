from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers.ia import IaReadSerializer
from ..utils.ia import get_ia


class IaAPIView(APIView):
    """
    API view for getting ia data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ia = get_ia()
        serializer = IaReadSerializer(ia, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
