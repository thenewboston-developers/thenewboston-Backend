from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from thenewboston.general.pagination import CustomPageNumberPagination

from ..models import Course
from ..serializers.course import CourseReadSerializer


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Course.objects.all().order_by('-created_date')
    serializer_class = CourseReadSerializer
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated]
