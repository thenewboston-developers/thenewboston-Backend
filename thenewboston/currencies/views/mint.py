from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..serializers.mint import MintSerializer


class MintMixin:
    """Mixin to add minting functionality to CurrencyViewSet"""

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def mint(self, request, pk=None):
        currency = self.get_object()
        serializer = MintSerializer(data=request.data, context={'request': request, 'currency': currency})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)
