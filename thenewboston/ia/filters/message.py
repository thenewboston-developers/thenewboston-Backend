import django_filters

from ..models import Message


class MessageFilter(django_filters.FilterSet):
    sender = django_filters.CharFilter(field_name='sender', lookup_expr='exact')

    class Meta:
        model = Message
        fields = ('sender',)
