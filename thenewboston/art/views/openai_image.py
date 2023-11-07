import openai
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..serializers.openai_image import OpenAIImageSerializer


class OpenAIImageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def create(request):
        openai.api_key = settings.OPENAI_API_KEY
        serializer = OpenAIImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = openai.Image.create(
            n=serializer.validated_data['quantity'],
            prompt=serializer.validated_data['description'],
            size='1024x1024',
        )

        return Response(response, status=status.HTTP_200_OK)
