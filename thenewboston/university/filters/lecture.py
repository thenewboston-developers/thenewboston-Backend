import django_filters

from ..models import Lecture
from ..models.base import PublicationStatus


class LectureFilter(django_filters.FilterSet):
    course_id = django_filters.NumberFilter(field_name='course__id', lookup_expr='exact')
    publication_status = django_filters.ChoiceFilter(choices=PublicationStatus.choices)

    class Meta:
        model = Lecture
        fields = ('course_id',)
