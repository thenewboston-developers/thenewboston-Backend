# custom imports
import re

import requests
from rest_framework import serializers

from ..models import Course, Lecture
from ..serializers.course import CourseReadSerializer

# -------------------


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

    class Meta:
        model = Lecture
        fields = ('course_id', 'description', 'name', 'publication_status', 'position', 'thumbnail_url', 'youtube_id')

    def validate_course_id(self, value):
        request = self.context.get('request')
        if Course.objects.filter(id=value, instructor=request.user).exists():
            return value
        raise serializers.ValidationError('You do not have access to add lecture in this course.')

    # Suggestions to validate the youtube_id to be valid youtube video url
    def validate_youtube_id(self, url):
        api_key = 'AIzaSyD5gTHht3VqVL5q_puTq0Cu75AftWy4xTE'  # Should be changed
        youtube_regex = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+$')

        if not youtube_regex.match(url):
            raise serializers.ValidationError('Invalid YouTube URL format.')

        video_id_match = re.search(r'v=([a-zA-Z0-9_-]{11})', url)
        if not video_id_match:
            raise serializers.ValidationError('No valid video ID found in the URL.')

        video_id = video_id_match.group(1)

        api_url = f'https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=id&key={api_key}'
        response = requests.get(api_url)

        if response.status_code != 200:
            message = response.text
            raise serializers.ValidationError(message)

        data = response.json()
        if len(data.get('items', [])) > 0:
            return url
        raise serializers.ValidationError('No valid video ID found in the URL.')
