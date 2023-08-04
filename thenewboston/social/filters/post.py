import django_filters

from ..models import Post


class PostFilter(django_filters.FilterSet):
    owner = django_filters.CharFilter(field_name='owner', lookup_expr='exact')

    class Meta:
        model = Post
        fields = ('owner',)
