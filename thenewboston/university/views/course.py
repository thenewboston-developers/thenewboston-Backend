from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectInstructorOrReadOnly

from ..filters.course import CourseFilter
from ..models import Course
from ..serializers.course import CourseReadSerializer, CourseWriteSerializer


class CourseViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = CourseFilter
    pagination_class = CustomPageNumberPagination
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated, IsObjectInstructorOrReadOnly]
    queryset = Course.objects.all().order_by('-created_date')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        read_serializer = CourseReadSerializer(course, context={'request': request})
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=partial)
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        read_serializer = CourseReadSerializer(course, context={'request': request})

        return Response(read_serializer.data)

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update', 'update']:
            return CourseWriteSerializer

        return CourseReadSerializer
