from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.enums import NotificationType
from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.views.base import CustomGenericViewSet
from thenewboston.notifications.models import Notification
from thenewboston.users.serializers.user import UserReadSerializer
from thenewboston.wallets.models import Wallet

from ..constants import SPECIAL_PRICES
from ..enums import ChallengeStatus, MatchEventType, MatchStatus, MoveType, SpecialType
from ..exceptions import ConflictError, GoneError
from ..models import (
    ConnectFiveChallenge,
    ConnectFiveEscrow,
    ConnectFiveMatch,
    ConnectFiveMatchEvent,
    ConnectFiveMatchPlayer,
)
from ..serializers import (
    ConnectFiveChallengeReadSerializer,
    ConnectFiveMatchReadSerializer,
    ConnectFiveMoveSerializer,
    ConnectFivePurchaseSerializer,
)
from ..services.clocks import apply_elapsed_time, switch_turn, touch_turn
from ..services.escrow import create_escrow, get_wallet_for_update, lock_stake, purchase_special
from ..services.match import finish_match_connect5, finish_match_draw, finish_match_resign, finish_match_timeout
from ..services.rules import apply_move, check_win, is_draw
from ..services.streaming import stream_challenge_update, stream_match_update


class ConnectFiveMatchViewSet(ListModelMixin, RetrieveModelMixin, CustomGenericViewSet):
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated]
    queryset = ConnectFiveMatch.objects.select_related(
        'active_player',
        'active_player__connect_five_stats',
        'challenge',
        'challenge__currency',
        'player_a',
        'player_a__connect_five_stats',
        'player_b',
        'player_b__connect_five_stats',
    ).order_by('-created_date')
    serializer_class = ConnectFiveMatchReadSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        mine_filter = self.request.query_params.get('mine')
        if mine_filter in {'1', 'self', 'true'}:
            queryset = queryset.filter(Q(player_a=user) | Q(player_b=user))
        elif mine_filter == 'exclude':
            queryset = queryset.exclude(Q(player_a=user) | Q(player_b=user))

        if status_filter := self.request.query_params.get('status'):
            queryset = queryset.filter(status=status_filter)

        return queryset

    @action(detail=True, methods=['post'], url_path='move')
    def move(self, request, pk=None):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"

        with transaction.atomic():
            match = (
                ConnectFiveMatch.objects.select_for_update()
                .select_related('challenge', 'player_a', 'player_b')
                .get(pk=pk)
            )

            if match.status != MatchStatus.ACTIVE:
                raise GoneError({'detail': 'Match is no longer active.'})

            if request.user.id not in {match.player_a_id, match.player_b_id}:
                raise PermissionDenied({'detail': 'You are not a participant in this match.'})

            if match.active_player_id != request.user.id:
                raise PermissionDenied({'detail': 'It is not your turn.'})

            remaining, now = apply_elapsed_time(match)
            if remaining <= 0:
                winner = match.player_b if match.active_player_id == match.player_a_id else match.player_a
                finish_match_timeout(match=match, winner=winner)
                stream_match_update(match=match, request=request)
                raise GoneError({'detail': 'Match ended due to timeout.'})

            serializer = ConnectFiveMoveSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            move_type = serializer.validated_data['move_type']
            x = serializer.validated_data['x']
            y = serializer.validated_data['y']

            match_player = ConnectFiveMatchPlayer.objects.select_for_update().get(match=match, user=request.user)
            player_value = 1 if request.user.id == match.player_a_id else 2

            if move_type != MoveType.SINGLE:
                inventory_field = _get_inventory_field(move_type)
                if not inventory_field:
                    raise ValidationError({'detail': 'Invalid move type.'})
                if getattr(match_player, inventory_field) <= 0:
                    raise ValidationError({'detail': 'No inventory available for this special.'})

            board_state, placed_positions, removed_positions = apply_move(
                board_state=match.board_state,
                move_type=move_type,
                player_value=player_value,
                x=x,
                y=y,
            )

            if move_type != MoveType.SINGLE:
                inventory_field = _get_inventory_field(move_type)
                setattr(match_player, inventory_field, getattr(match_player, inventory_field) - 1)

            match.board_state = board_state

            if move_type != MoveType.BOMB:
                if check_win(board_state=board_state, player_value=player_value, positions=placed_positions):
                    finish_match_connect5(match=match, winner=request.user)
                elif is_draw(board_state=board_state):
                    finish_match_draw(match=match)
                else:
                    switch_turn(match, now=now)
            else:
                switch_turn(match, now=now)

            match.save(
                update_fields=[
                    'active_player',
                    'board_state',
                    'clock_a_remaining_ms',
                    'clock_b_remaining_ms',
                    'turn_number',
                    'turn_started_at',
                    'modified_date',
                ]
            )
            match_player.save(
                update_fields=[
                    'inventory_bomb',
                    'inventory_h2',
                    'inventory_v2',
                    'modified_date',
                ]
            )

            ConnectFiveMatchEvent.objects.create(
                match=match,
                actor=request.user,
                event_type=MatchEventType.MOVE,
                payload={
                    'move_type': move_type,
                    'placed': placed_positions,
                    'removed': removed_positions,
                },
            )

            response_data = ConnectFiveMatchReadSerializer(match, context={'request': request}).data
            stream_match_update(match=match, request=request, match_data=response_data)

            return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='purchase')
    def purchase(self, request, pk=None):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"

        with transaction.atomic():
            match = (
                ConnectFiveMatch.objects.select_for_update()
                .select_related('challenge', 'player_a', 'player_b')
                .get(pk=pk)
            )
            escrow = ConnectFiveEscrow.objects.select_for_update().get(challenge=match.challenge)

            if match.status != MatchStatus.ACTIVE:
                raise GoneError({'detail': 'Match is no longer active.'})

            if request.user.id not in {match.player_a_id, match.player_b_id}:
                raise PermissionDenied({'detail': 'You are not a participant in this match.'})

            remaining, now = apply_elapsed_time(match)
            if remaining <= 0:
                winner = match.player_b if match.active_player_id == match.player_a_id else match.player_a
                finish_match_timeout(match=match, winner=winner)
                stream_match_update(match=match, request=request)
                raise GoneError({'detail': 'Match ended due to timeout.'})

            serializer = ConnectFivePurchaseSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            special_type = serializer.validated_data['special_type']
            quantity = serializer.validated_data['quantity']

            unit_price = SPECIAL_PRICES[special_type]
            cost = unit_price * quantity

            match_player = ConnectFiveMatchPlayer.objects.select_for_update().get(match=match, user=request.user)
            if match_player.spent_total + cost > match.max_spend_amount:
                raise ValidationError({'detail': 'Max spend exceeded.'})

            wallet = get_wallet_for_update(user=request.user, currency=match.challenge.currency)
            purchase_special(
                escrow=escrow,
                wallet=wallet,
                amount=cost,
            )

            match_player.spent_total += cost
            inventory_field = _get_inventory_field(special_type)
            if not inventory_field:
                raise ValidationError({'detail': 'Invalid special type.'})
            setattr(match_player, inventory_field, getattr(match_player, inventory_field) + quantity)

            match.prize_pool_total = escrow.total
            touch_turn(match, now=now)

            match.save(
                update_fields=[
                    'clock_a_remaining_ms',
                    'clock_b_remaining_ms',
                    'prize_pool_total',
                    'turn_started_at',
                    'modified_date',
                ]
            )
            match_player.save(
                update_fields=[
                    'inventory_bomb',
                    'inventory_h2',
                    'inventory_v2',
                    'spent_total',
                    'modified_date',
                ]
            )

            ConnectFiveMatchEvent.objects.create(
                match=match,
                actor=request.user,
                event_type=MatchEventType.PURCHASE,
                payload={'special_type': special_type, 'quantity': quantity, 'total_cost': cost},
            )

            response_data = ConnectFiveMatchReadSerializer(match, context={'request': request}).data
            stream_match_update(match=match, request=request, match_data=response_data)

            return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='resign')
    def resign(self, request, pk=None):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"

        with transaction.atomic():
            match = (
                ConnectFiveMatch.objects.select_for_update()
                .select_related('challenge', 'player_a', 'player_b')
                .get(pk=pk)
            )

            if match.status != MatchStatus.ACTIVE:
                raise GoneError({'detail': 'Match is no longer active.'})

            if request.user.id not in {match.player_a_id, match.player_b_id}:
                raise PermissionDenied({'detail': 'You are not a participant in this match.'})

            remaining, _ = apply_elapsed_time(match)
            if remaining <= 0:
                winner = match.player_b if match.active_player_id == match.player_a_id else match.player_a
                finish_match_timeout(match=match, winner=winner)
                response_data = ConnectFiveMatchReadSerializer(match, context={'request': request}).data
                stream_match_update(match=match, request=request, match_data=response_data)
                raise GoneError({'detail': 'Match ended due to timeout.'})

            winner = match.player_b if request.user.id == match.player_a_id else match.player_a
            finish_match_resign(match=match, resigning_player=request.user, winner=winner)

            response_data = ConnectFiveMatchReadSerializer(match, context={'request': request}).data
            stream_match_update(match=match, request=request, match_data=response_data)

            return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='rematch')
    def rematch(self, request, pk=None):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"

        with transaction.atomic():
            match = (
                ConnectFiveMatch.objects.select_for_update()
                .select_related('challenge', 'challenge__currency', 'player_a', 'player_b')
                .get(pk=pk)
            )

            if match.status not in {
                MatchStatus.DRAW,
                MatchStatus.FINISHED_CONNECT5,
                MatchStatus.FINISHED_RESIGN,
                MatchStatus.FINISHED_TIMEOUT,
            }:
                raise ConflictError({'detail': 'Rematches are only available for completed matches.'})

            if request.user.id not in {match.player_a_id, match.player_b_id}:
                raise PermissionDenied({'detail': 'You are not a participant in this match.'})

            if existing_rematch := _get_latest_rematch(match):
                if existing_rematch.status == ChallengeStatus.PENDING:
                    response_data = ConnectFiveChallengeReadSerializer(
                        existing_rematch, context={'request': request}
                    ).data
                    return Response(response_data, status=status.HTTP_200_OK)
                raise ConflictError({'detail': 'Rematch is no longer available.'})

            opponent = match.player_b if request.user.id == match.player_a_id else match.player_a
            currency = match.challenge.currency
            stake_amount = match.challenge.stake_amount

            try:
                challenger_wallet = get_wallet_for_update(user=request.user, currency=currency)
                opponent_wallet = get_wallet_for_update(user=opponent, currency=currency)
            except ValidationError as error:
                raise ConflictError({'detail': 'Insufficient funds for rematch.'}) from error

            if challenger_wallet.balance < stake_amount or opponent_wallet.balance < stake_amount:
                raise ConflictError({'detail': 'Insufficient funds for rematch.'})

            challenge = ConnectFiveChallenge.objects.create(
                challenger=request.user,
                opponent=opponent,
                currency=currency,
                stake_amount=stake_amount,
                max_spend_amount=match.max_spend_amount,
                time_limit_seconds=match.time_limit_seconds,
                status=ChallengeStatus.PENDING,
                expires_at=timezone.now(),
                rematch_for=match,
            )
            escrow = create_escrow(challenge=challenge)
            lock_stake(escrow=escrow, wallet=challenger_wallet, amount=stake_amount)

            response_data = ConnectFiveChallengeReadSerializer(challenge, context={'request': request}).data
            notification = Notification(
                owner=opponent,
                payload={
                    'challenger': UserReadSerializer(request.user, context={'request': request}).data,
                    'challenge': response_data,
                    'challenge_id': challenge.id,
                    'expires_at': challenge.expires_at.isoformat(),
                    'max_spend_amount': challenge.max_spend_amount,
                    'notification_type': NotificationType.CONNECT_FIVE_CHALLENGE.value,
                    'stake_amount': challenge.stake_amount,
                    'time_limit_seconds': challenge.time_limit_seconds,
                },
            )
            notification.save(should_stream=True)

            stream_challenge_update(challenge=challenge, request=request, challenge_data=response_data)

            return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='rematch-status')
    def rematch_status(self, request, pk=None):
        match = ConnectFiveMatch.objects.select_related('challenge', 'challenge__currency', 'player_a', 'player_b').get(
            pk=pk
        )

        if match.status not in {
            MatchStatus.DRAW,
            MatchStatus.FINISHED_CONNECT5,
            MatchStatus.FINISHED_RESIGN,
            MatchStatus.FINISHED_TIMEOUT,
        }:
            raise ConflictError({'detail': 'Rematches are only available for completed matches.'})

        if request.user.id not in {match.player_a_id, match.player_b_id}:
            raise PermissionDenied({'detail': 'You are not a participant in this match.'})

        latest_rematch = _get_latest_rematch(match)
        has_funds = _has_rematch_funds(match)
        response_data = {
            'can_rematch': not latest_rematch and has_funds,
            'challenge': (
                ConnectFiveChallengeReadSerializer(latest_rematch, context={'request': request}).data
                if latest_rematch
                else None
            ),
            'insufficient_funds': not has_funds,
        }

        return Response(response_data, status=status.HTTP_200_OK)


def _get_inventory_field(move_type):
    mapping = {
        MoveType.BOMB: 'inventory_bomb',
        MoveType.H2: 'inventory_h2',
        MoveType.V2: 'inventory_v2',
        SpecialType.BOMB: 'inventory_bomb',
        SpecialType.H2: 'inventory_h2',
        SpecialType.V2: 'inventory_v2',
    }
    return mapping.get(move_type)


def _get_latest_rematch(match):
    return (
        ConnectFiveChallenge.objects.filter(
            rematch_for=match,
        )
        .select_related('challenger', 'currency', 'opponent')
        .order_by('-created_date')
        .first()
    )


def _has_rematch_funds(match):
    stake_amount = match.challenge.stake_amount
    wallets = {
        wallet.owner_id: wallet
        for wallet in Wallet.objects.filter(
            currency=match.challenge.currency,
            owner__in=[match.player_a_id, match.player_b_id],
        )
    }
    if match.player_a_id not in wallets or match.player_b_id not in wallets:
        return False

    return wallets[match.player_a_id].balance >= stake_amount and wallets[match.player_b_id].balance >= stake_amount
