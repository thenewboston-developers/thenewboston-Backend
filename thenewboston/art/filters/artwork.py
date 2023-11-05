import django_filters

from ..models import Artwork


class ArtworkFilter(django_filters.FilterSet):
    owner = django_filters.CharFilter(field_name='owner', lookup_expr='exact')
    price_amount__isnull = django_filters.BooleanFilter(field_name='price_amount', lookup_expr='isnull')
    price_core__isnull = django_filters.BooleanFilter(field_name='price_core', lookup_expr='isnull')

    class Meta:
        model = Artwork
        fields = ('owner', 'price_amount__isnull', 'price_core__isnull')
