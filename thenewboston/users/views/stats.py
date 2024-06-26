from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers.stats import StatsSerializer


class StatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        User = get_user_model()
        user = get_object_or_404(User, id=user_id)
        serializer = StatsSerializer(user, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
