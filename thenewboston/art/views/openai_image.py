import promptlayer
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..serializers.openai_image import OpenAIImageSerializer

promptlayer.api_key = settings.PROMPTLAYER_API_KEY
OpenAI = promptlayer.openai.OpenAI


class OpenAIImageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def create(request):
        serializer = OpenAIImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.images.generate(
                model='dall-e-2',
                n=serializer.validated_data['quantity'],
                prompt=serializer.validated_data['description'],
                quality='standard',
                size='1024x1024',
            )
            return Response(response.dict(), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
