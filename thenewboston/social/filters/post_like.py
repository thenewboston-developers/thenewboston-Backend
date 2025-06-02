import django_filters

from ..models import PostLike


class PostLikeFilter(django_filters.FilterSet):
    post = django_filters.NumberFilter(field_name='post', lookup_expr='exact', required=True)

    class Meta:
        model = PostLike
        fields = ('post',)
