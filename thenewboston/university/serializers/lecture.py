from rest_framework import serializers

from ..models import Lecture
from ..models.base import PublicationStatus
from ..serializers.course import CourseReadSerializer


class LectureReadSerializer(serializers.ModelSerializer):
    course = CourseReadSerializer(read_only=True)

    class Meta:
        model = Lecture
        fields = (
            'id', 'course', 'name', 'description', 'publication_status', 'youtube_id', 'position', 'thumbnail_url',
            'duration_seconds', 'created_date', 'modified_date'
        )
        read_only_fields = (
            'id', 'course', 'name', 'description', 'publication_status', 'youtube_id', 'position', 'thumbnail_url',
            'duration_seconds', 'created_date', 'modified_date'
        )


class LectureWriteSerializer(serializers.ModelSerializer):

    course_id = serializers.IntegerField(required=True)
    publication_status = serializers.BooleanField()

    class Meta:
        model = Lecture
        fields = ('course_id', 'description', 'name', 'publication_status', 'thumbnail_url', 'youtube_id')

    def validate_publication_status(self, value):
        if value:
            return PublicationStatus.PUBLISHED
        return PublicationStatus.DRAFT
