from rest_framework import serializers

from ..models import Lecture
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
