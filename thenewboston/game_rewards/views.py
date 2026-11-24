from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import MAX_DEPOSIT, contribute, fund_summary


class DepositSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1, max_value=MAX_DEPOSIT)
    request_id = serializers.UUIDField()


class GameFundView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(fund_summary())


class GameFundDepositView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        deposit, fund = contribute(user=request.user, **serializer.validated_data)
        return Response(
            {'id': deposit.pk, 'amount': deposit.amount, 'currency': 'TNB', 'fund': fund_summary(fund)},
            status=status.HTTP_201_CREATED,
        )
