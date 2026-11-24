from django.db.models import Count, F, Sum, Window
from django.db.models.functions import Rank
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.users.models import User

from .serializers import GameEarningsLeaderboardSerializer, GameEarningsQuerySerializer
from .services import MAX_DEPOSIT, contribute, fund_summary


class DepositSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1, max_value=MAX_DEPOSIT)
    request_id = serializers.UUIDField()


class GameEarningsLeaderboardPagination(CustomPageNumberPagination):
    page_size = 25
    max_page_size = 100


class GameEarningsLeaderboardView(ListAPIView):
    filter_backends = []
    pagination_class = GameEarningsLeaderboardPagination
    permission_classes = [AllowAny]
    serializer_class = GameEarningsLeaderboardSerializer

    def get_queryset(self):
        query = GameEarningsQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        # The permanent payout ledger excludes guests, unfunded wins and PvP stakes.
        # Rank before pagination so ties retain the same rank on every page.
        return (
            User.objects.filter(
                gamerewarddecision__game=query.validated_data['game'],
                gamerewarddecision__status='paid',
            )
            .only('id', 'username', 'avatar')
            .annotate(
                rewarded_wins=Count('gamerewarddecision'),
                total_earned=Sum('gamerewarddecision__amount'),
            )
            .annotate(rank=Window(expression=Rank(), order_by=F('total_earned').desc()))
            .order_by('-total_earned', 'username', 'id')
        )


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
