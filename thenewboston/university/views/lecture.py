from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from thenewboston.general.pagination import CustomPageNumberPagination

from ..filters.lecture import LectureFilter
from ..models import Lecture
from ..serializers.lecture import LectureReadSerializer


class LectureViewSet(viewsets.ReadOnlyModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = LectureFilter
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    queryset = Lecture.objects.all().order_by('-created_date')
    serializer_class = LectureReadSerializer
