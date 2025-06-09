from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..filters.total_amount_minted import TotalAmountMintedFilter
from ..models import Currency
from ..serializers.total_amount_minted import TotalAmountMintedSerializer


class TotalAmountMintedView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        filterset = TotalAmountMintedFilter(request.GET, queryset=Currency.objects.all())

        if not filterset.is_valid():
            return Response(filterset.errors, status=status.HTTP_400_BAD_REQUEST)

        queryset = filterset.qs

        if not queryset.exists():
            return Response({'detail': 'Currency not found.'}, status=status.HTTP_404_NOT_FOUND)

        currency = queryset.first()
        serializer = TotalAmountMintedSerializer(currency)
        return Response(serializer.data)
