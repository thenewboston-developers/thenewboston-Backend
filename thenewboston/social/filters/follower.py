import django_filters

from ..models import Follower


class FollowerFilter(django_filters.FilterSet):
    follower = django_filters.CharFilter(field_name='follower', lookup_expr='exact')
    following = django_filters.CharFilter(field_name='following', lookup_expr='exact')

    class Meta:
        model = Follower
        fields = ('follower', 'following')
