import django_filters

from ..models import ArtworkTransfer


class ArtworkTransferFilter(django_filters.FilterSet):
    artwork = django_filters.CharFilter(field_name='artwork', lookup_expr='exact')

    class Meta:
        model = ArtworkTransfer
        fields = ('artwork',)
