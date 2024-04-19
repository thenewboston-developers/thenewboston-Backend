import django_filters

from ..models import Lecture


class LectureFilter(django_filters.FilterSet):
    course_id = django_filters.NumberFilter(field_name='course__id', lookup_expr='exact')

    class Meta:
        model = Lecture
        fields = ('course_id',)
