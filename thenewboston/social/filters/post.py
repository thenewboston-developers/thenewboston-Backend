import django_filters
from django.db import models

from ..models import Post


class PostFilter(django_filters.FilterSet):
    owner = django_filters.CharFilter(field_name='owner', lookup_expr='exact')
    user = django_filters.CharFilter(method='filter_user')

    class Meta:
        model = Post
        fields = ('owner', 'user')

    @staticmethod
    def filter_user(queryset, name, value):
        return queryset.filter(models.Q(owner=value) | models.Q(recipient=value))
