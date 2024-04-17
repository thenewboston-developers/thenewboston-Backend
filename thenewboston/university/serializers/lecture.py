from rest_framework import serializers

from ..models import Lecture


class LectureReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = Lecture
        fields = ['id', 'course', 'youtube_id', 'position', 'thumbnail_url', 'duration_seconds', 'name']
        read_only_fields = ['id', 'course', 'youtube_id', 'position', 'thumbnail_url', 'duration_seconds', 'name']
