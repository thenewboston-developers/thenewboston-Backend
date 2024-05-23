from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from ..models import Contribution
from ..serializers.contribution import ContributionSerializer, TopContributionSerializer


class ContributionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Contribution.objects.all()
    serializer_class = ContributionSerializer


class TopContributorsViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Contribution.objects.all()
    serializer_class = TopContributionSerializer

    def get_queryset(self):
        return self.get_contributions_queryset()

    def get_contributions_queryset(self):
        queryset = super().get_queryset()
        filter_type = self.request.query_params.get('filter-type', None)
        if filter_type == 'today':
            queryset = queryset.filter(created_date__date=timezone.now().date())
        elif filter_type == 'week':
            last_week = timezone.now() - timedelta(days=7)
            queryset = queryset.filter(created_date__date__gte=last_week.date())
        elif filter_type not in ['none', 'all']:
            queryset = queryset.none()
        queryset = queryset.values('user_id', 'user__username', 'user__avatar',
                                   'core__logo').annotate(total=Sum('reward_amount')).order_by('-total')[:5]
        return queryset
