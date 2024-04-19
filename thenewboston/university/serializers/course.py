from rest_framework import serializers

from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Course


class CourseReadSerializer(serializers.ModelSerializer):
    instructor = UserReadSerializer(read_only=True)

    class Meta:
        model = Course
        fields = (
            'id',
            'name',
            'description',
            'publication_status',
            'thumbnail',
            'instructor',
            'created_date',
            'modified_date',
        )
        read_only_fields = (
            'id', 'name', 'description', 'publication_status', 'thumbnail', 'instructor', 'created_date',
            'modified_date'
        )
