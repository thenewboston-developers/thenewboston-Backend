from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import Contribution
from ..serializers.contribution import ContributionSerializer, TopContributionSerializer


class ContributionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Contribution.objects.all()
    serializer_class = ContributionSerializer

    @action(detail=False, url_path='top')
    def get_top_contributions(self, request):
        queryset = self.get_contributions_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(data=serializer.data)

    def get_serializer_class(self):
        if self.action == 'get_top_contributions':
            return TopContributionSerializer
        return super().get_serializer_class()

    def get_contributions_queryset(self):
        queryset = super().get_queryset()
        filter_type = self.request.query_params.get('type', 'none')
        if filter_type == 'today':
            queryset = queryset.filter(created_date__date=timezone.now().date())
        elif filter_type == 'week':
            last_week = timezone.now() - timedelta(days=7)
            queryset = queryset.filter(created_date__date__gte=last_week.date())
        queryset = queryset.values('user_id', 'user__username', 'user__avatar',
                                   'core__logo').annotate(total=Sum('reward_amount')).order_by('-total')[:4]
        return queryset
