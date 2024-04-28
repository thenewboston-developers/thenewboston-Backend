from rest_framework import serializers

from ..models import Course, Lecture
from ..models.base import PublicationStatus
from ..serializers.course import CourseReadSerializer


class LectureReadSerializer(serializers.ModelSerializer):
    course = CourseReadSerializer(read_only=True)

    class Meta:
        model = Lecture
        fields = (
            'id', 'course', 'name', 'description', 'publication_status', 'youtube_id', 'position', 'thumbnail_url',
            'created_date', 'modified_date'
        )
        read_only_fields = (
            'id', 'course', 'name', 'description', 'publication_status', 'youtube_id', 'position', 'thumbnail_url',
            'created_date', 'modified_date'
        )


class LectureWriteSerializer(serializers.ModelSerializer):

    course_id = serializers.IntegerField(required=True)
    publication_status = serializers.BooleanField()

    class Meta:
        model = Lecture
        fields = ('course_id', 'description', 'name', 'publication_status', 'position', 'thumbnail_url', 'youtube_id')

    def validate_course_id(self, value):
        request = self.context.get('request')
        if Course.objects.filter(id=value, instructor=request.user).exists():
            return value
        raise serializers.ValidationError('You do not have access to add lecture in this course.')

    def validate_publication_status(self, value):
        if value:
            return PublicationStatus.PUBLISHED
        return PublicationStatus.DRAFT
