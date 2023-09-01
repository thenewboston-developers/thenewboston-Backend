import django_filters

from ..models import Artwork


class ArtworkFilter(django_filters.FilterSet):
    owner = django_filters.CharFilter(field_name='owner', lookup_expr='exact')

    class Meta:
        model = Artwork
        fields = ('owner',)
