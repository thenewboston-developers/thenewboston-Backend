import django_filters

from ..models import Course
from ..models.base import PublicationStatus


class CourseFilter(django_filters.FilterSet):
    instructor_id = django_filters.NumberFilter(field_name='instructor__id', lookup_expr='exact')
    publication_status = django_filters.ChoiceFilter(choices=PublicationStatus.choices)

    class Meta:
        model = Course
        fields = (
            'instructor_id',
            'publication_status',
        )
