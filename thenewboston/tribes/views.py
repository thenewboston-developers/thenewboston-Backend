from django.db import transaction
from django.utils.decorators import method_decorator
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Tournament
from .services import (
    activity_page,
    get_state,
    messages_page,
    perform_action,
    set_emblem,
    sweep_tournaments,
    tournament_summary,
)


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class StateView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response(
            get_state(user=request.user, tournament_id=request.query_params.get('tournament_id'), request=request)
        )


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class TournamentsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        sweep_tournaments()
        query = Tournament.objects.order_by('-id')
        if 'before' in request.query_params:
            before = serializers.IntegerField(min_value=1).run_validation(request.query_params['before'])
            query = query.filter(pk__lt=before)
        return Response([tournament_summary(s, request.user) for s in query[:100]])


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class ActionView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            state = perform_action(request.user, request.data, request)
        except PermissionDenied as exc:
            # Authentication is checked before this view. This marker means the
            # command itself was definitively rejected after receipt lookup, so
            # clients may clear its durable retry without confusing an expired
            # session with an unknown financial result.
            return Response({'detail': str(exc.detail), 'code': 'tribes_action_forbidden'}, status=403)
        return Response(state)


class EmblemSerializer(serializers.Serializer):
    image = serializers.ImageField()
    tournament_id = serializers.IntegerField(min_value=1)


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class EmblemView(APIView):
    parser_classes = (MultiPartParser,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = EmblemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(set_emblem(request.user, request=request, **serializer.validated_data))


class ActivityView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        tournament_id = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('tournament_id'))
        before = None
        if 'before' in request.query_params:
            before = serializers.IntegerField(min_value=1).run_validation(request.query_params['before'])
        return Response(activity_page(request.user, tournament_id, before, request))


class MessagesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        tournament_id = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('tournament_id'))
        before = None
        if 'before' in request.query_params:
            before = serializers.IntegerField(min_value=1).run_validation(request.query_params['before'])
        return Response(messages_page(request.user, tournament_id, before, request))
