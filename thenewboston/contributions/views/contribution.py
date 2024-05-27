import django_filters
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.utils.database import apply_on_commit

from ..models import Contribution
from ..serializers.contribution import ContributionSerializer
from ..tasks import reward_manual_contributions_task

AUTHENTICATED_USER_VALUES = ('me', 'self')


class ContributionFilterSet(django_filters.FilterSet):
    user_id = django_filters.CharFilter(method='filter_user_id')

    class Meta:
        model = Contribution
        fields = ['user_id']

    def filter_user_id(self, queryset, name, value):
        if value in AUTHENTICATED_USER_VALUES:
            user = self.request.user
            if user.is_authenticated:
                value = user.id
            else:
                return queryset.none()
        else:
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValidationError({
                    'user_id': 'must be integer or one of {}'.format(', '.join(AUTHENTICATED_USER_VALUES))
                })

        return queryset.filter(user_id=value)


class IsContributionWriteAllowed(BasePermission):

    def has_permission(self, request, view):
        user = request.user
        return bool(
            request.method in SAFE_METHODS or user and user.is_authenticated and user.is_manual_contribution_allowed
        )


class ContributionViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsContributionWriteAllowed]
    queryset = Contribution.objects.order_by('-created_date')
    serializer_class = ContributionSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ContributionFilterSet

    def perform_create(self, serializer):
        super().perform_create(serializer)
        apply_on_commit(
            lambda contribution_id=serializer.instance.id: reward_manual_contributions_task.delay(contribution_id)
        )
