from rest_framework import serializers

from ..models import Lecture
from ..serializers.course import CourseReadSerializer


class LectureReadSerializer(serializers.ModelSerializer):
    course = CourseReadSerializer(read_only=True)

    class Meta:
        model = Lecture
        fields = ['id', 'course', 'youtube_id', 'position', 'thumbnail_url', 'duration_seconds', 'name']
        read_only_fields = ['id', 'course', 'youtube_id', 'position', 'thumbnail_url', 'duration_seconds', 'name']
