from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Season
from .services import activity_page, get_state, messages_page, perform_action, season_summary, tick_world


class StateView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_state(user=request.user, season_id=request.query_params.get('season_id')))


class SeasonsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        tick_world()
        query = Season.objects.order_by('-id')
        if 'before' in request.query_params:
            before = serializers.IntegerField(min_value=1).run_validation(request.query_params['before'])
            query = query.filter(pk__lt=before)
        return Response([season_summary(s) for s in query[:100]])


class ActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            state = perform_action(request.user, request.data)
        except PermissionDenied as exc:
            # Authentication is checked before this view. This marker means the
            # command itself was definitively rejected after receipt lookup, so
            # clients may clear its durable retry without confusing an expired
            # session with an unknown financial result.
            return Response({'detail': str(exc.detail), 'code': 'tribes_action_forbidden'}, status=403)
        return Response(state)


class ActivityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        season_id = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('season_id'))
        before = None
        if 'before' in request.query_params:
            before = serializers.IntegerField(min_value=1).run_validation(request.query_params['before'])
        return Response(activity_page(request.user, season_id, before))


class MessagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        season_id = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('season_id'))
        before = None
        if 'before' in request.query_params:
            before = serializers.IntegerField(min_value=1).run_validation(request.query_params['before'])
        return Response(messages_page(request.user, season_id, before))
