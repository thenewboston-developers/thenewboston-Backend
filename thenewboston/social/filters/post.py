import django_filters
from django.db import models

from ..models import Post, PostImage


class PostFilter(django_filters.FilterSet):
    has_image = django_filters.BooleanFilter(method='filter_has_image')
    owner = django_filters.CharFilter(field_name='owner', lookup_expr='exact')
    user = django_filters.CharFilter(method='filter_user')

    class Meta:
        model = Post
        fields = ('has_image', 'owner', 'user')

    @staticmethod
    def filter_has_image(queryset, name, value):
        if value is None:
            return queryset

        has_image = models.Exists(PostImage.objects.filter(post=models.OuterRef('pk')))
        return queryset.filter(has_image if value else ~has_image)

    @staticmethod
    def filter_user(queryset, name, value):
        return queryset.filter(models.Q(owner=value) | models.Q(recipient=value))
