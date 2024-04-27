from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectCourseInstructorOrReadOnly

from ..filters.lecture import LectureFilter
from ..models import Lecture
from ..serializers.lecture import LectureReadSerializer, LectureWriteSerializer


class LectureViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = LectureFilter
    permission_classes = [IsAuthenticated, IsObjectCourseInstructorOrReadOnly]
    pagination_class = CustomPageNumberPagination
    parser_classes = (MultiPartParser, FormParser)
    queryset = Lecture.objects.all().order_by('position', '-created_date')
    serializer_class = LectureReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        lecture = serializer.save()
        read_serializer = LectureReadSerializer(lecture)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        lecture = serializer.save()
        read_serializer = LectureReadSerializer(lecture)

        return Response(read_serializer.data)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return LectureWriteSerializer

        return LectureReadSerializer
