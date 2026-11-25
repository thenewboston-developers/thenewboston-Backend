from functools import wraps

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CasinoBet
from .registry import registry
from .services import (
    MAX_AMOUNT,
    CasinoError,
    bet_receipt,
    casino_summary,
    commitment_receipt,
    create_commitment,
    fund_summary,
    move_funds,
    place_bet,
)


def casino_errors(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except CasinoError as exc:
            return Response(exc.data, status=exc.status)

    return wrapped


class WholeIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        # IntegerField ordinarily accepts strings and 1.0; casino coin amounts must be JSON integers.
        if type(data) is not int:
            self.fail('invalid')
        return super().to_internal_value(data)


class MovementSerializer(serializers.Serializer):
    amount = WholeIntegerField(min_value=1, max_value=MAX_AMOUNT)
    request_id = serializers.UUIDField()


class BetSerializer(MovementSerializer):
    commitment_id = serializers.UUIDField()
    client_seed = serializers.CharField(min_length=1, max_length=128, trim_whitespace=False)
    game = serializers.ChoiceField(choices=[])
    rules_version = WholeIntegerField(min_value=1)
    selection = serializers.JSONField(required=False, default=dict)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['game'].choices = [definition.game for definition in registry.games]


class CasinoView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(casino_summary(request.user))


class CommitmentView(APIView):
    permission_classes = [IsAuthenticated]

    @casino_errors
    def post(self, request):
        return Response(commitment_receipt(create_commitment(user=request.user)), status=status.HTTP_201_CREATED)


class BetsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        bets = CasinoBet.objects.filter(user=request.user).select_related('commitment').order_by('-id')[:20]
        return Response([bet_receipt(bet) for bet in bets])

    @casino_errors
    def post(self, request):
        serializer = BetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bet, fund, wallet = place_bet(user=request.user, **serializer.validated_data)
        return Response(bet_receipt(bet, fund=fund, wallet_balance=wallet.balance), status=status.HTTP_201_CREATED)


class BetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, request_id):
        bet = CasinoBet.objects.select_related('commitment').filter(user=request.user, request_id=request_id).first()
        if bet is None:
            return Response({'code': 'not_found', 'detail': 'No accepted bet has this request ID.'}, status=404)
        return Response(bet_receipt(bet))


class FundDepositView(APIView):
    permission_classes = [IsAdminUser]
    kind = 'deposit'

    @casino_errors
    def post(self, request):
        serializer = MovementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry, fund, wallet = move_funds(user=request.user, kind=self.kind, **serializer.validated_data)
        return Response(
            {
                'id': entry.pk,
                'kind': entry.kind,
                'amount': entry.amount,
                'fund': fund_summary(fund),
                'wallet_balance': wallet.balance,
            },
            status=status.HTTP_201_CREATED,
        )


class FundWithdrawalView(FundDepositView):
    kind = 'withdrawal'
