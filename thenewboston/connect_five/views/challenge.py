from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.enums import NotificationType
from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.views.base import CustomGenericViewSet
from thenewboston.notifications.models import Notification
from thenewboston.users.serializers.user import UserReadSerializer

from ..constants import TIME_LIMIT_CHOICES
from ..enums import ChallengeStatus, MatchEventType
from ..exceptions import ConflictError, GoneError
from ..models import ConnectFiveChallenge, ConnectFiveEscrow, ConnectFiveMatchEvent
from ..serializers import ConnectFiveChallengeCreateSerializer, ConnectFiveChallengeReadSerializer
from ..services.elo import get_or_create_stats
from ..services.escrow import (
    accept_stake,
    create_escrow,
    get_default_currency,
    get_wallet_for_update,
    lock_stake,
    refund_challenge,
)
from ..services.streaming import stream_challenge_update, stream_match_update


class ConnectFiveChallengeViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, CustomGenericViewSet):
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated]
    queryset = ConnectFiveChallenge.objects.select_related(
        'challenger',
        'challenger__connect_five_stats',
        'currency',
        'opponent',
        'opponent__connect_five_stats',
    ).order_by('-created_date')
    serializer_class = ConnectFiveChallengeReadSerializer
    serializer_classes = {'create': ConnectFiveChallengeCreateSerializer}

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        queryset = queryset.filter(Q(challenger=user) | Q(opponent=user))

        if status_filter := self.request.query_params.get('status'):
            queryset = queryset.filter(status=status_filter)

        mine_filter = self.request.query_params.get('mine')
        if mine_filter == 'sent':
            queryset = queryset.filter(challenger=user)
        elif mine_filter == 'received':
            queryset = queryset.filter(opponent=user)

        return queryset

    def create(self, request, *args, **kwargs):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"

        with transaction.atomic():
            serializer = self.get_serializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            validated_data = serializer.validated_data
            opponent = validated_data['opponent']
            stake_amount = validated_data['stake_amount']
            max_spend_amount = validated_data['max_spend_amount']
            time_limit_seconds = validated_data['time_limit_seconds']

            if time_limit_seconds not in TIME_LIMIT_CHOICES:
                raise ConflictError({'detail': 'Invalid time limit.'})

            currency = get_default_currency()
            wallet = get_wallet_for_update(user=request.user, currency=currency)

            challenge = ConnectFiveChallenge.objects.create(
                challenger=request.user,
                opponent=opponent,
                currency=currency,
                stake_amount=stake_amount,
                max_spend_amount=max_spend_amount,
                time_limit_seconds=time_limit_seconds,
                status=ChallengeStatus.PENDING,
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            escrow = create_escrow(challenge=challenge)
            lock_stake(escrow=escrow, wallet=wallet, amount=stake_amount)

            challenge_data = ConnectFiveChallengeReadSerializer(challenge, context={'request': request}).data
            notification = Notification(
                owner=opponent,
                payload={
                    'challenger': UserReadSerializer(request.user, context={'request': request}).data,
                    'challenge': challenge_data,
                    'challenge_id': challenge.id,
                    'expires_at': challenge.expires_at.isoformat(),
                    'max_spend_amount': max_spend_amount,
                    'notification_type': NotificationType.CONNECT_FIVE_CHALLENGE.value,
                    'stake_amount': stake_amount,
                    'time_limit_seconds': time_limit_seconds,
                },
            )
            notification.save(should_stream=True)

            stream_challenge_update(challenge=challenge, request=request, challenge_data=challenge_data)

            return Response(challenge_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, pk=None):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"

        with transaction.atomic():
            challenge = (
                ConnectFiveChallenge.objects.select_for_update()
                .select_related(
                    'challenger',
                    'currency',
                    'opponent',
                )
                .get(pk=pk)
            )
            escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=challenge)

            if challenge.status != ChallengeStatus.PENDING:
                raise ConflictError({'detail': 'Challenge is not pending.'})

            if challenge.opponent_id != request.user.id:
                raise PermissionDenied({'detail': 'Only the opponent can accept this challenge.'})

            if challenge.rematch_for_id is None and timezone.now() >= challenge.expires_at:
                wallet = get_wallet_for_update(user=challenge.challenger, currency=challenge.currency)
                challenge.status = ChallengeStatus.EXPIRED
                challenge.save(update_fields=['status', 'modified_date'])
                refund_challenge(escrow=escrow, wallet=wallet)
                stream_challenge_update(challenge=challenge, request=request)
                raise GoneError({'detail': 'Challenge has expired.'})

            try:
                wallet = get_wallet_for_update(user=request.user, currency=challenge.currency)
                accept_stake(
                    escrow=escrow,
                    wallet=wallet,
                    amount=challenge.stake_amount,
                )
            except ValidationError as error:
                if challenge.rematch_for_id:
                    raise ConflictError({'detail': 'Insufficient funds for rematch.'}) from error
                raise

            from ..models import ConnectFiveMatch, ConnectFiveMatchPlayer

            active_player = _get_active_player(challenge=challenge)
            match = ConnectFiveMatch.objects.create(
                challenge=challenge,
                player_a=challenge.challenger,
                player_b=challenge.opponent,
                active_player=active_player,
                clock_a_remaining_ms=challenge.time_limit_seconds * 1000,
                clock_b_remaining_ms=challenge.time_limit_seconds * 1000,
                prize_pool_total=escrow.total,
                max_spend_amount=challenge.max_spend_amount,
                time_limit_seconds=challenge.time_limit_seconds,
            )
            ConnectFiveMatchPlayer.objects.create(match=match, user=challenge.challenger)
            ConnectFiveMatchPlayer.objects.create(match=match, user=challenge.opponent)
            get_or_create_stats(user=challenge.challenger, for_update=True)
            get_or_create_stats(user=challenge.opponent, for_update=True)

            challenge.status = ChallengeStatus.ACCEPTED
            challenge.accepted_at = timezone.now()
            challenge.save(update_fields=['accepted_at', 'status', 'modified_date'])

            ConnectFiveMatchEvent.objects.create(
                match=match,
                actor=request.user,
                event_type=MatchEventType.CHALLENGE_ACCEPTED,
                payload={'challenge_id': challenge.id},
            )

            from ..serializers import ConnectFiveMatchReadSerializer

            response_data = ConnectFiveMatchReadSerializer(match, context={'request': request}).data
            stream_challenge_update(challenge=challenge, request=request)
            stream_match_update(match=match, request=request, match_data=response_data)

            return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"

        with transaction.atomic():
            challenge = (
                ConnectFiveChallenge.objects.select_for_update()
                .select_related('challenger', 'opponent', 'currency')
                .get(pk=pk)
            )
            escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=challenge)

            if challenge.status != ChallengeStatus.PENDING:
                raise ConflictError({'detail': 'Challenge is not pending.'})

            if challenge.challenger_id != request.user.id:
                raise PermissionDenied({'detail': 'Only the challenger can cancel.'})

            challenge.status = ChallengeStatus.CANCELLED
            challenge.save(update_fields=['status', 'modified_date'])

            wallet = get_wallet_for_update(user=challenge.challenger, currency=challenge.currency)
            refund_challenge(escrow=escrow, wallet=wallet)

            response_data = ConnectFiveChallengeReadSerializer(challenge, context={'request': request}).data
            stream_challenge_update(challenge=challenge, request=request, challenge_data=response_data)

            return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='decline')
    def decline(self, request, pk=None):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"

        with transaction.atomic():
            challenge = (
                ConnectFiveChallenge.objects.select_for_update()
                .select_related('challenger', 'opponent', 'currency')
                .get(pk=pk)
            )
            escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=challenge)

            if challenge.status != ChallengeStatus.PENDING:
                raise ConflictError({'detail': 'Challenge is not pending.'})

            if challenge.opponent_id != request.user.id:
                raise PermissionDenied({'detail': 'Only the opponent can decline.'})

            challenge.status = ChallengeStatus.DECLINED
            challenge.save(update_fields=['status', 'modified_date'])

            wallet = get_wallet_for_update(user=challenge.challenger, currency=challenge.currency)
            refund_challenge(escrow=escrow, wallet=wallet)

            response_data = ConnectFiveChallengeReadSerializer(challenge, context={'request': request}).data
            stream_challenge_update(challenge=challenge, request=request, challenge_data=response_data)

            return Response(response_data, status=status.HTTP_200_OK)


def _get_active_player(*, challenge):
    return challenge.opponent
