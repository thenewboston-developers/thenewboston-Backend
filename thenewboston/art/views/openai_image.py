import promptlayer
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.clients.openai import OpenAIClient

from ..serializers.openai_image import OpenAIImageSerializer

promptlayer.api_key = settings.PROMPTLAYER_API_KEY
OpenAI = promptlayer.openai.OpenAI


class OpenAIImageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def create(request):
        serializer = OpenAIImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        try:
            response = OpenAIClient.get_instance().generate_image(
                prompt=validated_data['description'],
                quantity=validated_data['quantity'],
            )
            # TODO(dmu) LOW: Consider using status.HTTP_201_CREATED instead
            return Response(response.dict(), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
