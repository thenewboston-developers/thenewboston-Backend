from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from thenewboston.general.guest_games import GameAccess, GuestGameResponseMixin, guest_session
from thenewboston.general.views.base import CustomGenericViewSet

from .models import BattleshipMatch
from .serializers import (
    MatchActionSerializer,
    MatchCreateSerializer,
    MatchFireSerializer,
    MatchPlaceSerializer,
    MatchReadSerializer,
)
from .services import advance_deadlines, create_match, perform_action


class MatchPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


class BattleshipMatchViewSet(GuestGameResponseMixin, ListModelMixin, RetrieveModelMixin, CustomGenericViewSet):
    permission_classes = [GameAccess]
    guest_actions = {'create', 'place', 'fire', 'resign', 'rematch'}
    public_read = False
    pagination_class = MatchPagination
    serializer_class = MatchReadSerializer
    queryset = BattleshipMatch.objects.select_related('host', 'guest').all()

    def get_queryset(self):
        user = self.request.user
        # Unlike public-information games, every endpoint is participant-only.
        session = guest_session(self.request)
        participants = Q(guest_session=session) if session else Q(host_id=user.id) | Q(guest_id=user.id)
        queryset = (
            super().get_queryset().filter(participants)
            if user.is_authenticated or session
            else super().get_queryset().none()
        )
        if statuses := self.request.query_params.get('status'):
            # Unknown values are ignored instead of reaching the database.
            queryset = queryset.filter(status__in=set(statuses.split(',')) & set(BattleshipMatch.Status.values))
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = MatchCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        match = create_match(
            user=request.user if request.user.is_authenticated else None,
            guest_session=guest_session(request),
            **serializer.validated_data,
        )
        match.refresh_from_db()
        return Response(self.get_serializer(match).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def retrieve(self, request, *args, **kwargs):
        self.queryset = self.queryset.select_for_update(of=('self',))
        match = self.get_object()
        advance_deadlines(match)
        return Response(self.get_serializer(match).data)

    @transaction.atomic
    def _perform(self, request, action_name, serializer_class=MatchActionSerializer):
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.queryset = self.queryset.select_for_update(of=('self',))
        match = perform_action(
            self.get_object(),
            request.user if request.user.is_authenticated else None,
            action_name,
            serializer.validated_data,
            guest_session(request),
        )
        match.refresh_from_db()
        return Response(self.get_serializer(match).data)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        return self._perform(request, 'accept')

    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        return self._perform(request, 'decline')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        return self._perform(request, 'cancel')

    @action(detail=True, methods=['post'])
    def place(self, request, pk=None):
        return self._perform(request, 'place', MatchPlaceSerializer)

    @action(detail=True, methods=['post'])
    def fire(self, request, pk=None):
        return self._perform(request, 'fire', MatchFireSerializer)

    @action(detail=True, methods=['post'])
    def resign(self, request, pk=None):
        return self._perform(request, 'resign')

    @action(detail=True, methods=['post'])
    def rematch(self, request, pk=None):
        return self._perform(request, 'rematch')
